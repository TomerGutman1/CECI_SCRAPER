#!/usr/bin/env python3
"""
Batch script for adding special category tags to all government decisions.

Processes ~25K records by year with checkpointing and progress tracking.

Usage:
    python bin/add_special_tags.py --preview          # Preview on 10 records
    python bin/add_special_tags.py --dry-run          # Full dry-run
    python bin/add_special_tags.py --execute          # Execute (all years)
    python bin/add_special_tags.py --execute --year 2024  # Single year
    python bin/add_special_tags.py --resume           # Resume from checkpoint
    python bin/add_special_tags.py --retry            # Retry previously skipped records
    python bin/add_special_tags.py --restore --backup-file PATH  # Restore backup

Options:
    --preview             Preview on 10 records
    --dry-run             Full dry-run (no DB changes)
    --execute             Execute changes
    --year YYYY           Process specific year only
    --resume              Resume from last checkpoint
    --retry               Retry previously skipped/failed records
    --no-review           Only add special tags, don't review existing
    --restore             Restore from backup file
    --backup-file PATH    Backup file to restore from
    --verbose             Verbose logging
"""

import sys
import os
import argparse
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.processors.qa import (
    fetch_records_for_qa,
    fix_special_category_tags,
    QAScanResult,
)
from src.gov_scraper.processors.ai import SPECIAL_CATEGORY_TAGS

# Paths
CHECKPOINT_FILE = os.path.join(PROJECT_ROOT, 'data', 'special_tags_checkpoint.json')
SKIPPED_FILE = os.path.join(PROJECT_ROOT, 'data', 'special_tags_skipped.json')
BACKUP_DIR = os.path.join(PROJECT_ROOT, 'data', 'backups')
REPORT_DIR = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, 'special_tags.log'),
                encoding='utf-8'
            )
        ]
    )
    return logging.getLogger(__name__)


def load_checkpoint() -> Dict:
    """Load checkpoint from file."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "current_year": None,
        "completed_years": [],
        "total_processed": 0,
        "total_updated": 0,
        "special_tags_count": {tag: 0 for tag in SPECIAL_CATEGORY_TAGS},
        "tags_fixed": 0,
        "errors": 0,
        "skipped_keys": [],
        "started_at": None,
    }


def load_skipped_keys() -> List[str]:
    """Load list of skipped decision keys."""
    if os.path.exists(SKIPPED_FILE):
        with open(SKIPPED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_skipped_keys(keys: List[str]):
    """Save skipped decision keys to file for later completion."""
    os.makedirs(os.path.dirname(SKIPPED_FILE), exist_ok=True)
    with open(SKIPPED_FILE, 'w', encoding='utf-8') as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)


def append_skipped_keys(new_keys: List[str]):
    """Append new skipped keys to existing list."""
    existing = load_skipped_keys()
    # Avoid duplicates
    existing_set = set(existing)
    for key in new_keys:
        if key not in existing_set:
            existing.append(key)
            existing_set.add(key)
    save_skipped_keys(existing)


def save_checkpoint(checkpoint: Dict):
    """Save checkpoint to file."""
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def clear_checkpoint():
    """Clear checkpoint file."""
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


def backup_year(year: int, records: List[Dict], logger) -> str:
    """Backup records before processing."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"special_tags_{year}_{timestamp}.json")

    backup_data = [
        {
            "decision_key": r.get("decision_key"),
            "tags_policy_area": r.get("tags_policy_area", ""),
        }
        for r in records
    ]

    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Backed up {len(records)} records to {backup_path}")
    return backup_path


def restore_backup(backup_path: str, logger):
    """Restore records from backup."""
    from src.gov_scraper.processors.tag_migration import batch_update_records

    if not os.path.exists(backup_path):
        logger.error(f"Backup file not found: {backup_path}")
        return False

    with open(backup_path, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)

    updates = [
        (r["decision_key"], {"tags_policy_area": r["tags_policy_area"]})
        for r in backup_data
    ]

    logger.info(f"Restoring {len(updates)} records from backup...")
    success, errors = batch_update_records(updates)
    logger.info(f"Restored {success} records, {len(errors)} errors")

    return len(errors) == 0


def process_year(
    year: int,
    dry_run: bool = True,
    review_existing: bool = True,
    logger=None
) -> Dict:
    """Process all records for a specific year."""
    if logger is None:
        logger = logging.getLogger(__name__)

    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    logger.info(f"\n{'='*60}")
    logger.info(f"Processing year {year}")
    logger.info(f"{'='*60}")

    # Fetch records
    logger.info(f"Fetching records for {year}...")
    records = fetch_records_for_qa(
        start_date=start_date,
        end_date=end_date,
    )
    logger.info(f"Found {len(records)} records")

    if not records:
        return {
            "year": year,
            "total": 0,
            "updated": 0,
            "special_tags": {},
            "tags_fixed": 0,
            "errors": 0,
        }

    # Backup before processing (only in execute mode)
    if not dry_run:
        backup_year(year, records, logger)

    # Process with fixer
    logger.info(f"Running special category tagger (review_existing={review_existing})...")
    updates, result = fix_special_category_tags(
        records,
        dry_run=dry_run,
        review_existing=review_existing
    )

    # Return stats including skipped keys for later retry
    return {
        "year": year,
        "total": result.total_scanned,
        "updated": result.issues_found,
        "special_tags": result.summary.get("special_tags_added", {}),
        "tags_fixed": result.summary.get("existing_tags_fixed", 0),
        "errors": result.summary.get("errors", 0),
        "applied": result.summary.get("applied", 0) if not dry_run else 0,
        "skipped_keys": result.summary.get("skipped_keys", []),
    }


def run_batch(
    years: List[int],
    dry_run: bool = True,
    review_existing: bool = True,
    resume: bool = False,
    logger=None
):
    """Run batch processing for multiple years."""
    if logger is None:
        logger = logging.getLogger(__name__)

    # Load or initialize checkpoint
    if resume:
        checkpoint = load_checkpoint()
        if not checkpoint.get("started_at"):
            logger.warning("No checkpoint found. Starting fresh.")
            checkpoint = load_checkpoint()
    else:
        checkpoint = load_checkpoint()
        checkpoint["completed_years"] = []
        checkpoint["started_at"] = datetime.now().isoformat()

    # Filter out completed years if resuming
    if resume and checkpoint.get("completed_years"):
        years = [y for y in years if y not in checkpoint["completed_years"]]
        logger.info(f"Resuming. Skipping completed years: {checkpoint['completed_years']}")

    if not years:
        logger.info("All years already processed!")
        return

    logger.info(f"\n{'#'*60}")
    logger.info(f"Special Category Tags Batch Processing")
    logger.info(f"{'#'*60}")
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Review existing tags: {review_existing}")
    logger.info(f"Years to process: {years}")
    logger.info(f"{'#'*60}\n")

    total_stats = {
        "total_processed": 0,
        "total_updated": 0,
        "special_tags": {tag: 0 for tag in SPECIAL_CATEGORY_TAGS},
        "tags_fixed": 0,
        "errors": 0,
        "skipped_keys": [],
    }

    for year in years:
        try:
            checkpoint["current_year"] = year
            save_checkpoint(checkpoint)

            year_stats = process_year(year, dry_run, review_existing, logger)

            # Update totals
            total_stats["total_processed"] += year_stats["total"]
            total_stats["total_updated"] += year_stats["updated"]
            total_stats["tags_fixed"] += year_stats["tags_fixed"]
            total_stats["errors"] += year_stats["errors"]

            # Accumulate skipped keys
            year_skipped = year_stats.get("skipped_keys", [])
            if year_skipped:
                total_stats["skipped_keys"].extend(year_skipped)
                logger.info(f"    Skipped: {len(year_skipped)} (will retry later)")

            for tag, count in year_stats.get("special_tags", {}).items():
                total_stats["special_tags"][tag] = total_stats["special_tags"].get(tag, 0) + count

            # Mark year complete
            checkpoint["completed_years"].append(year)
            checkpoint["total_processed"] = total_stats["total_processed"]
            checkpoint["total_updated"] = total_stats["total_updated"]
            checkpoint["special_tags_count"] = total_stats["special_tags"]
            checkpoint["tags_fixed"] = total_stats["tags_fixed"]
            checkpoint["errors"] = total_stats["errors"]
            save_checkpoint(checkpoint)

            # Log year summary
            logger.info(f"\n  Year {year} complete:")
            logger.info(f"    Processed: {year_stats['total']}")
            logger.info(f"    Updated: {year_stats['updated']}")
            for tag, count in year_stats.get("special_tags", {}).items():
                if count > 0:
                    logger.info(f"    {tag}: +{count}")

            # Cooldown between years
            if not dry_run and years.index(year) < len(years) - 1:
                logger.info(f"  Cooldown: 60 seconds...")
                time.sleep(60)

        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")
            total_stats["errors"] += 1
            checkpoint["errors"] = total_stats["errors"]
            save_checkpoint(checkpoint)
            continue

    # Save skipped keys for later retry
    if total_stats["skipped_keys"]:
        append_skipped_keys(total_stats["skipped_keys"])
        logger.info(f"\nSaved {len(total_stats['skipped_keys'])} skipped keys to: {SKIPPED_FILE}")

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total processed: {total_stats['total_processed']}")
    logger.info(f"Total updated: {total_stats['total_updated']}")
    logger.info(f"Existing tags fixed: {total_stats['tags_fixed']}")
    logger.info(f"Errors: {total_stats['errors']}")
    logger.info(f"Skipped (for retry): {len(total_stats['skipped_keys'])}")
    logger.info(f"\nSpecial tags added:")
    for tag, count in total_stats["special_tags"].items():
        logger.info(f"  {tag}: {count}")

    # Export final report
    os.makedirs(REPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_str = "dry_run" if dry_run else "execute"
    report_path = os.path.join(REPORT_DIR, f"special_tags_batch_{mode_str}_{timestamp}.json")

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "mode": mode_str,
            "review_existing": review_existing,
            "years_processed": checkpoint.get("completed_years", []),
            "stats": total_stats,
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"\nReport saved to: {report_path}")

    # Clear checkpoint if execute mode completed successfully
    if not dry_run and total_stats["errors"] == 0:
        clear_checkpoint()
        logger.info("Checkpoint cleared (batch complete)")


def main():
    parser = argparse.ArgumentParser(
        description="Batch add special category tags to government decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python bin/add_special_tags.py --preview
    python bin/add_special_tags.py --dry-run
    python bin/add_special_tags.py --execute
    python bin/add_special_tags.py --execute --year 2024
    python bin/add_special_tags.py --resume
    python bin/add_special_tags.py --restore --backup-file data/backups/special_tags_2024_xxx.json
        """
    )

    # Mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--preview", action="store_true", help="Preview on 10 records")
    mode_group.add_argument("--dry-run", action="store_true", help="Full dry-run")
    mode_group.add_argument("--execute", action="store_true", help="Execute changes")
    mode_group.add_argument("--retry", action="store_true", help="Retry skipped records")
    mode_group.add_argument("--restore", action="store_true", help="Restore from backup")

    # Options
    parser.add_argument("--year", type=int, help="Process specific year only")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--no-review", action="store_true", help="Only add special tags")
    parser.add_argument("--backup-file", type=str, help="Backup file to restore")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logger = setup_logging(args.verbose)

    # Handle restore mode
    if args.restore:
        if not args.backup_file:
            logger.error("--backup-file required for restore mode")
            return
        backup_path = args.backup_file
        if not os.path.isabs(backup_path):
            backup_path = os.path.join(PROJECT_ROOT, backup_path)
        restore_backup(backup_path, logger)
        return

    # Handle retry mode - process previously skipped records
    if args.retry:
        skipped_keys = load_skipped_keys()
        if not skipped_keys:
            logger.info("No skipped records to retry.")
            return

        logger.info(f"\n{'='*60}")
        logger.info(f"RETRY MODE: Processing {len(skipped_keys)} skipped records")
        logger.info(f"{'='*60}")

        # Fetch records by decision_key
        from src.gov_scraper.db.connector import get_supabase_client
        client = get_supabase_client()

        all_records = []
        # Fetch in batches of 100
        for i in range(0, len(skipped_keys), 100):
            batch_keys = skipped_keys[i:i+100]
            resp = client.table('israeli_government_decisions').select(
                'decision_key, decision_title, decision_content, decision_date, tags_policy_area, summary'
            ).in_('decision_key', batch_keys).execute()
            if resp.data:
                all_records.extend(resp.data)

        logger.info(f"Found {len(all_records)} of {len(skipped_keys)} records")

        if not all_records:
            logger.info("No records found to retry.")
            return

        # Process with fixer
        updates, result = fix_special_category_tags(
            all_records,
            dry_run=False,
            review_existing=not args.no_review
        )

        logger.info(f"\nRetry Results:")
        logger.info(f"  Processed: {result.total_scanned}")
        logger.info(f"  Updated: {result.issues_found}")
        logger.info(f"  Errors: {result.summary.get('errors', 0)}")

        # Update skipped file - keep only records that still failed
        still_failed = result.summary.get("skipped_keys", [])
        if still_failed:
            save_skipped_keys(still_failed)
            logger.info(f"  Still failing: {len(still_failed)} (saved for next retry)")
        else:
            # All succeeded - clear skipped file
            if os.path.exists(SKIPPED_FILE):
                os.remove(SKIPPED_FILE)
            logger.info("  All retries successful! Cleared skipped file.")

        return

    # Handle preview mode
    if args.preview:
        logger.info("Preview mode: processing 10 records from 2024")
        records = fetch_records_for_qa(
            start_date="2024-01-01",
            end_date="2024-12-31",
            max_records=10,
        )
        if records:
            updates, result = fix_special_category_tags(
                records,
                dry_run=True,
                review_existing=not args.no_review
            )
            logger.info(f"\nPreview Results:")
            logger.info(f"  Processed: {result.total_scanned}")
            logger.info(f"  Would update: {result.issues_found}")
            for issue in result.issues[:10]:
                logger.info(f"  {issue.decision_key}: {issue.description}")
        return

    # Determine years to process
    if args.year:
        years = [args.year]
    else:
        # All years from 2026 down to 1993
        years = list(range(2026, 1992, -1))

    # Run batch
    dry_run = args.dry_run or args.preview
    review_existing = not args.no_review

    # Confirmation for execute mode
    if args.execute and not args.resume:
        print(f"\nAbout to process {len(years)} years with EXECUTE mode.")
        print("This will modify the database.")
        confirm = input("Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return

    run_batch(
        years=years,
        dry_run=dry_run,
        review_existing=review_existing,
        resume=args.resume,
        logger=logger
    )


if __name__ == "__main__":
    main()
