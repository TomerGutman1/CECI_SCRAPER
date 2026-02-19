#!/usr/bin/env python3
"""
Full-scale local scraper for production deployment.

Two-phase pipeline to avoid Gemini+Chrome httpx conflict:
  Phase A: Scrape all decision content with Chrome → save raw to intermediate file → close Chrome
  Phase B: Load raw scraped data → AI process each → save final output

Usage:
    python bin/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --verbose
    python bin/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --resume --verbose
    python bin/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --max-decisions 5 --verbose
    python bin/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --ai-only --verbose  # Skip scraping, run AI on existing raw data
"""

import argparse
import json
import logging
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

# Batch processing settings for anti-blocking (Phase A)
BATCH_SIZE = 10
BATCH_DELAY_MIN = 15.0
BATCH_DELAY_MAX = 30.0
MAX_CONSECUTIVE_BLOCKS = 3

# Save/checkpoint intervals
SCRAPE_SAVE_INTERVAL = 50   # Save raw scraped data every N decisions
AI_SAVE_INTERVAL = 50       # Save AI-processed data every N decisions
PROGRESS_REPORT_INTERVAL = 100
QUALITY_CHECK_INTERVAL = 500


def setup_logging(verbose=False):
    """Set up comprehensive logging."""
    from src.gov_scraper.config import LOG_DIR
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_path = os.path.join(LOG_DIR, "full_scraper.log")
    level = logging.DEBUG if verbose else logging.INFO

    file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


def load_manifest(manifest_path):
    """Load catalog manifest with all decision URLs."""
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    if not entries:
        raise ValueError("Empty manifest file")

    return entries


def save_results(output_path, processed_decisions, logger):
    """Save processed decisions as flat JSON list (compatible with push_local.py)."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(processed_decisions, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(processed_decisions)} decisions to {output_path}")


def save_checkpoint(output_path, start_index, processed_count, failed_count, failed_keys):
    """Save processing checkpoint for resume capability."""
    checkpoint_path = output_path.replace('.json', '_checkpoint.json')
    checkpoint_data = {
        'timestamp': datetime.now().isoformat(),
        'start_index': start_index,
        'processed_count': processed_count,
        'failed_count': failed_count,
        'failed_keys': failed_keys,
    }

    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)


def load_checkpoint(output_path):
    """Load processing checkpoint and existing results if resuming."""
    checkpoint_path = output_path.replace('.json', '_checkpoint.json')

    if not os.path.exists(checkpoint_path):
        return 0, [], []

    try:
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        start_index = data.get('start_index', 0) + data.get('processed_count', 0) + data.get('failed_count', 0)
        failed_keys = data.get('failed_keys', [])

        # Load existing results from output file
        existing_results = []
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
            if not isinstance(existing_results, list):
                existing_results = []

        return start_index, existing_results, failed_keys
    except Exception:
        return 0, [], []


def monitor_quality(decisions, logger):
    """Monitor processing quality in real-time using correct DB field names."""
    if not decisions:
        return 0.0

    total = len(decisions)
    with_policy_tags = sum(1 for d in decisions if d.get('tags_policy_area'))
    with_gov_bodies = sum(1 for d in decisions if d.get('tags_government_body'))
    with_summaries = sum(1 for d in decisions if d.get('summary') and len(d.get('summary', '')) > 50)
    with_content = sum(1 for d in decisions if d.get('decision_content') and len(d.get('decision_content', '')) > 100)

    policy_pct = (with_policy_tags / total * 100) if total > 0 else 0
    bodies_pct = (with_gov_bodies / total * 100) if total > 0 else 0
    summary_pct = (with_summaries / total * 100) if total > 0 else 0
    content_pct = (with_content / total * 100) if total > 0 else 0

    logger.info(f"QUALITY METRICS ({total} decisions):")
    logger.info(f"   Content: {content_pct:.1f}% | Policy Tags: {policy_pct:.1f}% | Gov Bodies: {bodies_pct:.1f}% | Summaries: {summary_pct:.1f}%")

    avg_quality = (policy_pct + bodies_pct + summary_pct + content_pct) / 4
    grade = "A" if avg_quality >= 85 else "B+" if avg_quality >= 75 else "B" if avg_quality >= 65 else "C+" if avg_quality >= 55 else "C"
    logger.info(f"   Grade: {grade} ({avg_quality:.1f}%)")

    return avg_quality


def get_raw_path(output_path):
    """Get path for intermediate raw scraped data file."""
    return output_path.replace('.json', '_raw.json')


def phase_a_scrape(entries_to_process, raw_path, start_index, total_entries, headless, logger):
    """
    Phase A: Scrape all decision content with Chrome, save raw data, close Chrome.

    No AI calls happen here — Chrome is fully closed before Phase B.
    Returns (scraped_data, failed_keys).
    """
    from src.gov_scraper.scrapers.decision import scrape_decision_with_url_recovery
    from src.gov_scraper.processors.qa import validate_scraped_content
    from src.gov_scraper.utils.selenium import SeleniumWebDriver

    # Load existing raw data if resuming
    scraped_data = []
    scraped_keys = set()
    if os.path.exists(raw_path):
        try:
            with open(raw_path, 'r', encoding='utf-8') as f:
                scraped_data = json.load(f)
            scraped_keys = {d.get('decision_key') for d in scraped_data}
            logger.info(f"Loaded {len(scraped_data)} existing raw entries from {raw_path}")
        except Exception:
            scraped_data = []

    failed_keys = []
    consecutive_blocks = 0
    new_scraped = 0
    start_time = time.time()

    logger.info(f"PHASE A: SCRAPING {len(entries_to_process)} decisions with Chrome")
    logger.info("-" * 60)

    with SeleniumWebDriver(headless=headless) as swd:
        for i, entry in enumerate(entries_to_process, 1):
            actual_index = start_index + i
            dec_num = entry.get('decision_number', '?')
            dec_key = entry.get('decision_key', '')

            # Skip already-scraped decisions
            if dec_key in scraped_keys:
                logger.debug(f"Skipping already-scraped decision #{dec_num}")
                continue

            logger.info(f"[{actual_index}/{total_entries}] Scraping decision #{dec_num}")

            # Batch cooldown for anti-blocking
            if new_scraped > 0 and new_scraped % BATCH_SIZE == 0:
                cooldown = random.uniform(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
                logger.info(f"Batch cooldown: {cooldown:.0f}s after {new_scraped} decisions")
                time.sleep(cooldown)

            try:
                decision_data = None
                max_retries = 2

                for retry in range(max_retries + 1):
                    wait_time = 15 + (retry * 10)
                    decision_data = scrape_decision_with_url_recovery(entry, wait_time=wait_time, swd=swd)

                    if not decision_data:
                        break

                    is_valid, error_msg = validate_scraped_content(decision_data)
                    if is_valid:
                        break

                    if retry < max_retries:
                        logger.warning(f"Content validation failed (attempt {retry + 1}): {error_msg} — retrying")
                    else:
                        logger.error(f"Content validation failed after {max_retries + 1} attempts: {error_msg}")
                        decision_data = None

                if not decision_data:
                    logger.warning(f"Failed to scrape decision #{dec_num} - skipping")
                    failed_keys.append(dec_key)
                    consecutive_blocks += 1

                    if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                        logger.error(f"{MAX_CONSECUTIVE_BLOCKS} consecutive failures — likely blocked. Stopping scraping.")
                        break
                    continue

                consecutive_blocks = 0
                scraped_data.append(decision_data)
                scraped_keys.add(dec_key)
                new_scraped += 1

                logger.info(f"Scraped decision #{dec_num} — content: {len(decision_data.get('decision_content', ''))} chars ({new_scraped} new)")

            except Exception as e:
                logger.error(f"Unexpected error scraping decision #{dec_num}: {e}")
                failed_keys.append(dec_key)
                continue

            # Incremental save
            if new_scraped > 0 and new_scraped % SCRAPE_SAVE_INTERVAL == 0:
                with open(raw_path, 'w', encoding='utf-8') as f:
                    json.dump(scraped_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Phase A checkpoint: saved {len(scraped_data)} raw entries")

            # Progress
            if new_scraped > 0 and new_scraped % PROGRESS_REPORT_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = new_scraped / elapsed * 3600
                remaining = len(entries_to_process) - i
                eta = remaining / (new_scraped / elapsed) if new_scraped > 0 else 0
                logger.info(f"SCRAPE PROGRESS: {i}/{len(entries_to_process)} ({i/len(entries_to_process)*100:.1f}%) — {rate:.0f}/hr — ETA {eta/3600:.1f}h")

    # Chrome closed via context manager

    # Final save of raw data
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(scraped_data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    logger.info(f"PHASE A COMPLETE: {new_scraped} new scraped, {len(scraped_data)} total, {len(failed_keys)} failed — {elapsed/60:.1f} min")
    return scraped_data, failed_keys


def phase_b_ai_process(scraped_data, output_path, logger):
    """
    Phase B: AI-process all scraped decisions (no Chrome running).

    Loads raw scraped data, runs Gemini AI + post-processing + prepare_for_database.
    Returns (processed_decisions, ai_failed_keys).
    """
    from src.gov_scraper.processors.ai import process_decision_with_ai
    from src.gov_scraper.processors.qa import apply_inline_fixes
    from src.gov_scraper.processors.incremental import prepare_for_database

    # Load existing processed data if resuming
    processed_decisions = []
    processed_keys = set()
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                processed_decisions = json.load(f)
            if isinstance(processed_decisions, list):
                processed_keys = {d.get('decision_key') for d in processed_decisions}
                logger.info(f"Loaded {len(processed_decisions)} existing processed entries from {output_path}")
            else:
                processed_decisions = []
        except Exception:
            processed_decisions = []

    ai_failed_keys = []
    new_processed = 0
    start_time = time.time()

    # Filter to only un-processed entries
    to_process = [d for d in scraped_data if d.get('decision_key') not in processed_keys]

    logger.info(f"PHASE B: AI PROCESSING {len(to_process)} decisions (no Chrome)")
    logger.info("-" * 60)

    for i, decision_data in enumerate(to_process, 1):
        dec_num = decision_data.get('decision_number', '?')
        dec_key = decision_data.get('decision_key', '')

        logger.info(f"[{i}/{len(to_process)}] AI processing decision #{dec_num}")

        try:
            processed_decision = process_decision_with_ai(decision_data)
            if not processed_decision:
                logger.warning(f"AI processing failed for decision #{dec_num} - skipping")
                ai_failed_keys.append(dec_key)
                continue

            final_decision = apply_inline_fixes(processed_decision)

            db_ready = prepare_for_database([final_decision])
            if not db_ready:
                logger.warning(f"prepare_for_database failed for decision #{dec_num} - skipping")
                ai_failed_keys.append(dec_key)
                continue

            processed_decisions.append(db_ready[0])
            processed_keys.add(dec_key)
            new_processed += 1

            logger.info(f"AI done: decision #{dec_num} ({new_processed}/{len(to_process)})")

        except Exception as e:
            logger.error(f"Unexpected error in AI processing for decision #{dec_num}: {e}")
            ai_failed_keys.append(dec_key)
            continue

        # Incremental save
        if new_processed > 0 and new_processed % AI_SAVE_INTERVAL == 0:
            save_results(output_path, processed_decisions, logger)
            logger.info(f"Phase B checkpoint: saved {len(processed_decisions)} processed entries")

        # Progress
        if new_processed > 0 and new_processed % PROGRESS_REPORT_INTERVAL == 0:
            elapsed = time.time() - start_time
            rate = new_processed / elapsed * 3600
            remaining = len(to_process) - i
            eta = remaining / (new_processed / elapsed) if new_processed > 0 else 0
            logger.info(f"AI PROGRESS: {i}/{len(to_process)} ({i/len(to_process)*100:.1f}%) — {rate:.0f}/hr — ETA {eta/3600:.1f}h")

        # Quality monitoring
        if new_processed > 0 and new_processed % QUALITY_CHECK_INTERVAL == 0:
            monitor_quality(processed_decisions[-QUALITY_CHECK_INTERVAL:], logger)

    elapsed = time.time() - start_time
    logger.info(f"PHASE B COMPLETE: {new_processed} AI-processed, {len(processed_decisions)} total, {len(ai_failed_keys)} failed — {elapsed/60:.1f} min")
    return processed_decisions, ai_failed_keys


def main():
    parser = argparse.ArgumentParser(description='Full-scale local scraper — 2-phase pipeline')
    parser.add_argument('--manifest', required=True, help='Path to catalog manifest JSON file')
    parser.add_argument('--output', required=True, help='Path to output JSON file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--max-decisions', type=int, help='Limit processing to N decisions (for testing)')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint (reuse existing raw/processed data)')
    parser.add_argument('--no-headless', action='store_true', help='Run Chrome in visible mode (required for Cloudflare bypass)')
    parser.add_argument('--ai-only', action='store_true', help='Skip scraping, run AI on existing raw data')

    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    logger.info("FULL-SCALE LOCAL SCRAPER — 2-PHASE PIPELINE")
    logger.info("=" * 80)
    logger.info(f"Manifest: {args.manifest}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Max decisions: {args.max_decisions or 'Unlimited'}")
    logger.info(f"Resume mode: {args.resume}")
    logger.info(f"AI-only mode: {args.ai_only}")
    logger.info(f"Headless: {not args.no_headless}")
    logger.info("=" * 80)

    # Validate Gemini API key (quick check, no API call — avoids httpx conflict)
    from src.gov_scraper.processors.ai import gemini_client
    if not gemini_client:
        logger.error("Gemini client not initialized - check GEMINI_API_KEY in .env")
        return False
    logger.info("Gemini client initialized (API will be tested on first AI call)")

    # Load manifest
    try:
        entries = load_manifest(args.manifest)
        logger.info(f"Loaded {len(entries)} entries from manifest")
    except Exception as e:
        logger.error(f"Failed to load manifest: {e}")
        return False

    # Prepare output directory
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    raw_path = get_raw_path(args.output)
    start_time = time.time()

    # Determine processing range
    start_index = 0
    entries_to_process = entries
    if args.max_decisions:
        entries_to_process = entries[:args.max_decisions]

    # ── PHASE A: SCRAPE ──────────────────────────────────────────────
    scrape_failed_keys = []
    if args.ai_only:
        logger.info("Skipping Phase A (--ai-only mode)")
        if not os.path.exists(raw_path):
            logger.error(f"No raw data file found at {raw_path} — cannot run AI-only mode")
            return False
        with open(raw_path, 'r', encoding='utf-8') as f:
            scraped_data = json.load(f)
        logger.info(f"Loaded {len(scraped_data)} raw entries for AI processing")
    else:
        scraped_data, scrape_failed_keys = phase_a_scrape(
            entries_to_process, raw_path, start_index, len(entries),
            headless=not args.no_headless, logger=logger,
        )
        if not scraped_data:
            logger.error("Phase A produced no scraped data — aborting")
            return False

    # ── PHASE B: AI PROCESS ──────────────────────────────────────────
    processed_decisions, ai_failed_keys = phase_b_ai_process(
        scraped_data, args.output, logger,
    )

    # ── FINAL REPORT ─────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    all_failed = scrape_failed_keys + ai_failed_keys
    total_attempted = len(entries_to_process)

    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"Total time: {elapsed_total/3600:.2f} hours")
    logger.info(f"Scraped: {len(scraped_data)} | AI-processed: {len(processed_decisions)}")
    logger.info(f"Scrape failures: {len(scrape_failed_keys)} | AI failures: {len(ai_failed_keys)}")
    if processed_decisions:
        success_rate = len(processed_decisions) / total_attempted * 100 if total_attempted > 0 else 0
        logger.info(f"Success rate: {success_rate:.1f}%")

    if processed_decisions:
        logger.info("FINAL QUALITY REPORT:")
        monitor_quality(processed_decisions, logger)

        # Save final results
        save_results(args.output, processed_decisions, logger)

        # Save metadata
        metadata_path = args.output.replace('.json', '_metadata.json')
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'total_scraped': len(scraped_data),
            'total_processed': len(processed_decisions),
            'scrape_failed': scrape_failed_keys,
            'ai_failed': ai_failed_keys,
            'processing_time_hours': elapsed_total / 3600,
            'source_manifest': args.manifest,
        }
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"Metadata saved to {metadata_path}")

        return True
    else:
        logger.error("No decisions were successfully processed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
