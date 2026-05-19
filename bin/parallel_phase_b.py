#!/usr/bin/env python3
"""Parallel Phase B: AI-process gov 25-37 decisions across multiple workers.

Each worker gets a chunk of decisions, processes them with Gemini AI,
and saves checkpoints independently. Results are merged at the end.

Usage:
    python3 bin/parallel_phase_b.py --workers 1 --max-decisions 5 --verbose
    python3 bin/parallel_phase_b.py --workers 4 --verbose
    python3 bin/parallel_phase_b.py --workers 4 --resume --verbose
"""
import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RAW_INPUT = PROJECT_ROOT / "data" / "scraped" / "production_api_raw.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "scraped" / "production_api_parallel.json"
CHECKPOINT_DIR = PROJECT_ROOT / "data" / "phase_b_checkpoints"
LOG_DIR = PROJECT_ROOT / "logs"

VALID_GOVS = {str(g) for g in range(25, 38)}  # 25-37 inclusive
CHECKPOINT_INTERVAL = 50
QUALITY_INTERVAL = 200
API_DELAY = 0.5  # seconds between API calls per worker


def setup_logger(name, log_file, verbose=False):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(ch)

    return logger


def load_checkpoint(checkpoint_file):
    """Load processed decisions from a worker checkpoint file."""
    if not checkpoint_file.exists():
        return [], set()
    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        keys = {d.get("decision_key") for d in data}
        return data, keys
    except Exception as e:
        logging.getLogger("checkpoint").error(
            f"CORRUPTED checkpoint {checkpoint_file}: {e} — starting fresh for this chunk"
        )
        return [], set()


def save_checkpoint(checkpoint_file, decisions):
    """Atomically save decisions to checkpoint file."""
    tmp = checkpoint_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)
    tmp.replace(checkpoint_file)


def monitor_quality(decisions, logger):
    """Log quality metrics for a batch of decisions."""
    if not decisions:
        return
    total = len(decisions)
    with_policy = sum(1 for d in decisions if d.get("tags_policy_area"))
    with_bodies = sum(1 for d in decisions if d.get("tags_government_body"))
    with_summary = sum(1 for d in decisions if d.get("summary") and len(d.get("summary", "")) > 50)
    with_content = sum(1 for d in decisions if d.get("decision_content") and len(d.get("decision_content", "")) > 100)

    pct = lambda n: n / total * 100
    avg = (pct(with_policy) + pct(with_bodies) + pct(with_summary) + pct(with_content)) / 4
    grade = "A" if avg >= 85 else "B+" if avg >= 75 else "B" if avg >= 65 else "C" if avg >= 55 else "D"
    logger.info(
        f"QUALITY ({total}): Content={pct(with_content):.0f}% Policy={pct(with_policy):.0f}% "
        f"Bodies={pct(with_bodies):.0f}% Summary={pct(with_summary):.0f}% — Grade: {grade} ({avg:.0f}%)"
    )


def worker_process(worker_id, chunk, checkpoint_dir, verbose):
    """Process a chunk of decisions in a separate process.

    Each worker imports AI modules fresh (spawn), creating its own Gemini client.
    Returns (worker_id, processed_count, failed_count, failed_keys).
    """
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    from src.gov_scraper.processors.ai import process_decision_with_ai
    from src.gov_scraper.processors.qa import apply_inline_fixes
    from src.gov_scraper.processors.incremental import prepare_for_database

    log_file = LOG_DIR / f"parallel_phase_b_worker_{worker_id}.log"
    logger = setup_logger(f"worker-{worker_id}", log_file, verbose)

    checkpoint_file = Path(checkpoint_dir) / f"worker_{worker_id}.json"

    # Load existing checkpoint for resume
    processed, processed_keys = load_checkpoint(checkpoint_file)
    skipped = 0

    # Filter out already-processed decisions
    remaining = [d for d in chunk if d.get("decision_key") not in processed_keys]
    skipped = len(chunk) - len(remaining)
    if skipped > 0:
        logger.info(f"Resumed: {skipped} already processed, {len(remaining)} remaining")

    failed_keys = []
    new_count = 0
    start_time = time.time()

    logger.info(f"Starting: {len(remaining)} decisions to process")

    for i, decision_data in enumerate(remaining, 1):
        dec_key = decision_data.get("decision_key", "?")
        dec_num = decision_data.get("decision_number", "?")

        try:
            result = process_decision_with_ai(decision_data)
            if not result:
                logger.warning(f"AI returned None for {dec_key}")
                failed_keys.append(dec_key)
                continue

            result = apply_inline_fixes(result)
            db_ready = prepare_for_database([result])
            if not db_ready:
                logger.warning(f"prepare_for_database failed for {dec_key}")
                failed_keys.append(dec_key)
                continue

            processed.append(db_ready[0])
            processed_keys.add(dec_key)
            new_count += 1

            if verbose:
                logger.debug(f"[{i}/{len(remaining)}] Done: {dec_key}")

        except Exception as e:
            logger.error(f"Error processing {dec_key}: {e}")
            failed_keys.append(dec_key)
            continue

        # Checkpoint
        if new_count > 0 and new_count % CHECKPOINT_INTERVAL == 0:
            save_checkpoint(checkpoint_file, processed)
            logger.info(f"Checkpoint: {len(processed)} saved ({new_count} new)")

        # Quality metrics
        if new_count > 0 and new_count % QUALITY_INTERVAL == 0:
            monitor_quality(processed[-QUALITY_INTERVAL:], logger)

        # Progress
        if new_count > 0 and new_count % 100 == 0:
            elapsed = time.time() - start_time
            rate = new_count / elapsed * 3600
            eta = (len(remaining) - i) / (new_count / elapsed) if new_count > 0 else 0
            logger.info(
                f"PROGRESS: {i}/{len(remaining)} ({i/len(remaining)*100:.1f}%) "
                f"— {rate:.0f}/hr — ETA {eta/3600:.1f}h"
            )

        # Rate limiting
        time.sleep(API_DELAY)

    # Final save
    save_checkpoint(checkpoint_file, processed)
    elapsed = time.time() - start_time
    logger.info(
        f"DONE: {new_count} new + {skipped} resumed = {len(processed)} total, "
        f"{len(failed_keys)} failed — {elapsed/60:.1f} min"
    )

    return worker_id, new_count, len(failed_keys), failed_keys


def split_round_robin(decisions, n_workers):
    """Split decisions into chunks via round-robin for even distribution."""
    # Sort by government_number descending for even spread
    decisions.sort(key=lambda d: int(d.get("government_number", "0")), reverse=True)
    chunks = [[] for _ in range(n_workers)]
    for i, d in enumerate(decisions):
        chunks[i % n_workers].append(d)
    return chunks


def merge_worker_outputs(checkpoint_dir, output_file, logger):
    """Merge all worker checkpoint files into final output."""
    all_decisions = []
    for f in sorted(checkpoint_dir.glob("worker_*.json")):
        if f.suffix == ".tmp":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            all_decisions.extend(data)
            logger.info(f"  {f.name}: {len(data)} decisions")
        except Exception as e:
            logger.error(f"  {f.name}: FAILED to read — {e}")

    # Sort by decision_key for deterministic output
    all_decisions.sort(key=lambda d: d.get("decision_key", ""))

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_decisions, f, ensure_ascii=False, indent=2)

    logger.info(f"Merged {len(all_decisions)} decisions → {output_file}")
    return all_decisions


def main():
    parser = argparse.ArgumentParser(description="Parallel Phase B: AI-process gov 25-37")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--max-decisions", type=int, help="Limit to N decisions (for testing)")
    parser.add_argument("--resume", action="store_true", help="Resume from existing checkpoints")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--merge-only", action="store_true", help="Skip processing, just merge existing checkpoints")
    args = parser.parse_args()

    # Setup
    LOG_DIR.mkdir(exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("main", LOG_DIR / "parallel_phase_b.log", args.verbose)

    logger.info("=" * 60)
    logger.info(f"PARALLEL PHASE B — {args.workers} workers")
    logger.info("=" * 60)

    # Merge-only mode
    if args.merge_only:
        logger.info("MERGE-ONLY mode — skipping AI processing")
        all_decisions = merge_worker_outputs(CHECKPOINT_DIR, OUTPUT_FILE, logger)
        # Run duplicate fixer
        from bin.fix_duplicate_keys import fix_file
        total, fixes, remaining = fix_file(str(OUTPUT_FILE))
        logger.info(f"Duplicate fixer: {total} records, {fixes} fixes, {remaining} remaining dups")
        return

    # Load raw data
    logger.info(f"Loading raw data from {RAW_INPUT}...")
    with open(RAW_INPUT, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    logger.info(f"Loaded {len(raw_data)} total records")

    # Filter to gov 25-37
    decisions = [d for d in raw_data if d.get("government_number") in VALID_GOVS]
    logger.info(f"Filtered to gov 25-37: {len(decisions)} decisions")

    # Distribution
    gov_counts = Counter(d.get("government_number") for d in decisions)
    for gov in sorted(gov_counts, key=lambda g: int(g), reverse=True):
        logger.info(f"  Gov {gov}: {gov_counts[gov]}")

    # Resume: collect already-processed keys from all checkpoints
    if args.resume:
        existing_keys = set()
        for f in CHECKPOINT_DIR.glob("worker_*.json"):
            if f.suffix == ".tmp":
                continue
            _, keys = load_checkpoint(f)
            existing_keys |= keys
        before = len(decisions)
        decisions = [d for d in decisions if d.get("decision_key") not in existing_keys]
        logger.info(f"RESUME: {before - len(decisions)} already processed, {len(decisions)} remaining")
    else:
        # Clean start — remove old checkpoints
        for f in CHECKPOINT_DIR.glob("worker_*.json"):
            f.unlink()
        for f in CHECKPOINT_DIR.glob("worker_*.tmp"):
            f.unlink()
        logger.info("Fresh start — cleared old checkpoints")

    # Limit decisions
    if args.max_decisions:
        decisions = decisions[:args.max_decisions]
        logger.info(f"Limited to {len(decisions)} decisions (--max-decisions)")

    if not decisions:
        logger.info("No decisions to process!")
        # Still merge if we have checkpoints
        if any(CHECKPOINT_DIR.glob("worker_*.json")):
            all_decisions = merge_worker_outputs(CHECKPOINT_DIR, OUTPUT_FILE, logger)
            from bin.fix_duplicate_keys import fix_file
            total, fixes, remaining = fix_file(str(OUTPUT_FILE))
            logger.info(f"Duplicate fixer: {total} records, {fixes} fixes, {remaining} remaining dups")
        return

    # Split into chunks
    n_workers = min(args.workers, len(decisions))
    chunks = split_round_robin(decisions, n_workers)
    for i, chunk in enumerate(chunks):
        gov_dist = Counter(d.get("government_number") for d in chunk)
        logger.info(f"  Worker {i}: {len(chunk)} decisions ({dict(sorted(gov_dist.items()))})")

    # Run workers
    logger.info(f"\nLaunching {n_workers} workers...")
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(
                worker_process, i, chunks[i], str(CHECKPOINT_DIR), args.verbose
            ): i
            for i in range(n_workers)
        }

        all_failed = []
        total_new = 0
        crashed_workers = []
        for future in as_completed(futures):
            wid = futures[future]
            try:
                worker_id, new_count, fail_count, failed_keys = future.result()
                total_new += new_count
                all_failed.extend(failed_keys)
                logger.info(f"Worker {worker_id} finished: {new_count} processed, {fail_count} failed")
            except Exception as e:
                logger.error(f"Worker {wid} CRASHED: {e}")
                crashed_workers.append(wid)

    elapsed = time.time() - start_time
    logger.info(f"\nAll workers done in {elapsed/60:.1f} min ({elapsed/3600:.1f} hours)")
    logger.info(f"Total new: {total_new}, Total failed: {len(all_failed)}")

    if crashed_workers:
        logger.error(f"WARNING: {len(crashed_workers)} worker(s) crashed: {crashed_workers}")
        logger.error("Output will be INCOMPLETE. Re-run with --resume to retry failed chunks.")

    if all_failed:
        logger.warning(f"Failed keys ({len(all_failed)}): {all_failed[:20]}{'...' if len(all_failed) > 20 else ''}")

    # Merge
    logger.info("\nMerging worker outputs...")
    all_decisions = merge_worker_outputs(CHECKPOINT_DIR, OUTPUT_FILE, logger)

    # Quality check on merged output
    logger.info("\nFinal quality check:")
    monitor_quality(all_decisions, logger)

    # Gov distribution in output
    out_govs = Counter(d.get("government_number") for d in all_decisions)
    for gov in sorted(out_govs, key=lambda g: int(g), reverse=True):
        logger.info(f"  Gov {gov}: {out_govs[gov]}")

    # Run duplicate fixer
    logger.info("\nRunning duplicate key fixer...")
    from bin.fix_duplicate_keys import fix_file
    total, fixes, remaining = fix_file(str(OUTPUT_FILE))
    logger.info(f"Duplicate fixer: {total} records, {fixes} fixes, {remaining} remaining dups")

    logger.info(f"\nDONE! Output: {OUTPUT_FILE} ({len(all_decisions)} decisions)")


if __name__ == "__main__":
    main()
