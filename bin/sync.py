#!/usr/bin/env python3
"""
Database sync script for Israeli Government Decisions.
Supports two modes:
  --use-api   (default) Chrome-free sync using gov.il REST APIs + curl_cffi
  (legacy)    Selenium-based sync for fallback
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime

# Add src to Python path for package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Basic imports (always available)
from gov_scraper.processors.ai import process_decision_with_ai
from gov_scraper.processors.incremental import prepare_for_database
from gov_scraper.db.dal import insert_decisions_batch, check_existing_decision_keys
from gov_scraper.processors.approval import get_user_approval
from gov_scraper.processors.qa import validate_decision_inline, validate_scraped_content, apply_inline_fixes
from gov_scraper.config import LOG_DIR, LOG_FILE, GOVERNMENT_NUMBER


def _import_selenium_modules():
    """Import selenium modules only when needed (legacy mode)."""
    from gov_scraper.scrapers.catalog import extract_decision_urls_from_catalog_selenium
    from gov_scraper.scrapers.decision import scrape_decision_with_url_recovery
    from gov_scraper.utils.selenium import SeleniumWebDriver, CloudflareBlockedError
    return extract_decision_urls_from_catalog_selenium, scrape_decision_with_url_recovery, SeleniumWebDriver, CloudflareBlockedError


def _import_api_modules():
    """Import API modules for Chrome-free sync."""
    from gov_scraper.scrapers.catalog import extract_catalog_via_api
    from gov_scraper.scrapers.decision import scrape_decision_via_api
    return extract_catalog_via_api, scrape_decision_via_api


# Anti-block: batch cooldown settings
BATCH_SIZE = 10
BATCH_DELAY_MIN = 15.0
BATCH_DELAY_MAX = 30.0
MAX_CONSECUTIVE_FAILURES = 3


def setup_logging(verbose=False):
    """Set up logging configuration."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_path = os.path.join(LOG_DIR, LOG_FILE)
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def _validate_gemini_key(logger):
    """Step 0: Validate Gemini API key. Returns True if valid, False otherwise."""
    logger.info("STEP 0: Validating Gemini API key...")
    try:
        from gov_scraper.processors.ai import gemini_client
        from gov_scraper.config import GEMINI_MODEL
        if not gemini_client:
            raise ValueError("Gemini client not initialized - API key is missing or invalid")

        gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents="test",
            config={"max_output_tokens": 5}
        )
        logger.info("Gemini API key validated successfully")
        return True
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            logger.warning("Gemini API is rate limited but key is valid.")
            return True
        else:
            logger.error(f"Gemini API key validation failed: {e}")
            print(f"\nERROR: Gemini API key is invalid or not working!")
            print(f"Details: {e}")
            print("\nPlease check your .env file and ensure GEMINI_API_KEY is set correctly.")
            return False


def _filter_new_entries(decision_entries, logger, max_decisions=None):
    """Step 2: Filter catalog entries to only new ones not in DB."""
    logger.info("STEP 2: Checking which entries already exist in database...")

    candidate_keys = []
    key_to_entry = {}
    for entry in decision_entries:
        dec_num = entry.get('decision_number', '')
        if dec_num:
            key = f"{GOVERNMENT_NUMBER}_{dec_num}"
            candidate_keys.append(key)
            key_to_entry[key] = entry

    existing_keys = check_existing_decision_keys(candidate_keys)
    logger.info(f"Found {len(existing_keys)} entries already in database out of {len(candidate_keys)} candidates")

    new_entries = [key_to_entry[k] for k in candidate_keys if k not in existing_keys]
    new_entries.sort(key=lambda e: (e.get('decision_date', ''), e.get('decision_number', '')))
    logger.info(f"Identified {len(new_entries)} new entries to process")

    if max_decisions is not None:
        new_entries = new_entries[:max_decisions]

    return new_entries, existing_keys


def _process_decisions_api(entries_to_process, logger):
    """Step 3 (API mode): Scrape content via Content Page API and run AI."""
    _, scrape_decision_via_api = _import_api_modules()
    from curl_cffi import requests as curl_requests

    processed_decisions = []
    failed_count = 0
    consecutive_failures = 0

    session = curl_requests.Session(impersonate="chrome")

    logger.info(f"Will process {len(entries_to_process)} new decisions via API (no Chrome)")

    for i, entry in enumerate(entries_to_process, 1):
        dec_num = entry.get('decision_number', '?')
        dec_url = entry.get('url', '')
        logger.info(f"Processing decision {i}/{len(entries_to_process)}: #{dec_num} {dec_url}")

        # Batch cooldown every BATCH_SIZE decisions
        if i > 1 and (i - 1) % BATCH_SIZE == 0:
            cooldown = random.uniform(2.0, 5.0)  # Shorter cooldown for API (no Cloudflare concern)
            logger.info(f"Batch cooldown: {cooldown:.1f}s after {i-1} decisions")
            time.sleep(cooldown)

        try:
            # Scrape content via Content Page API
            decision_data = None
            max_retries = 2

            for retry in range(max_retries + 1):
                decision_data = scrape_decision_via_api(entry, session=session)

                if not decision_data:
                    if retry < max_retries:
                        logger.warning(f"API scrape failed for #{dec_num} (attempt {retry + 1}), retrying...")
                        time.sleep(2 * (retry + 1))
                        continue
                    break

                is_valid, error_msg = validate_scraped_content(decision_data)
                if is_valid:
                    break

                if retry < max_retries:
                    logger.warning(f"Content validation failed for #{dec_num} (attempt {retry + 1}): {error_msg}")
                else:
                    logger.error(f"Content validation failed for #{dec_num} after {max_retries + 1} attempts: {error_msg}")
                    decision_data = None

            if not decision_data:
                logger.warning(f"Failed to get valid content for decision #{dec_num} - skipping")
                failed_count += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(f"{MAX_CONSECUTIVE_FAILURES} consecutive failures. Stopping.")
                    break
                continue

            consecutive_failures = 0

            # Process with AI
            logger.info(f"Processing decision #{dec_num} with AI...")
            decision_data = process_decision_with_ai(decision_data)

            # Post-AI fixes
            decision_data = apply_inline_fixes(decision_data)

            # QA validation (warnings only)
            qa_warnings = validate_decision_inline(decision_data)
            if qa_warnings:
                for warn in qa_warnings:
                    logger.warning(f"QA [{dec_num}]: {warn}")

            processed_decisions.append(decision_data)
            logger.info(f"Successfully processed decision #{dec_num}")

        except Exception as e:
            logger.error(f"Failed to process decision #{dec_num}: {e}")
            failed_count += 1
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error(f"{MAX_CONSECUTIVE_FAILURES} consecutive failures. Stopping.")
                break
            continue

    return processed_decisions, failed_count


def _process_decisions_selenium(entries_to_process, swd, logger):
    """Step 3 (Selenium mode): Scrape content via Chrome and run AI."""
    _, scrape_decision_with_url_recovery, _, CloudflareBlockedError = _import_selenium_modules()

    processed_decisions = []
    failed_count = 0
    consecutive_blocks = 0

    logger.info(f"Will process {len(entries_to_process)} new decisions via Selenium")

    for i, entry in enumerate(entries_to_process, 1):
        dec_num = entry.get('decision_number', '?')
        dec_url = entry.get('url', '')
        logger.info(f"Processing decision {i}/{len(entries_to_process)}: #{dec_num} {dec_url}")

        if i > 1 and (i - 1) % BATCH_SIZE == 0:
            cooldown = random.uniform(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
            logger.info(f"Batch cooldown: {cooldown:.0f}s after {i-1} decisions")
            time.sleep(cooldown)

        try:
            decision_data = None
            max_content_retries = 2

            for retry in range(max_content_retries + 1):
                wait_time = 15 + (retry * 10)
                decision_data = scrape_decision_with_url_recovery(entry, wait_time=wait_time, swd=swd)

                if not decision_data:
                    break

                is_valid, error_msg = validate_scraped_content(decision_data)
                if is_valid:
                    break

                if retry < max_content_retries:
                    logger.warning(f"Content validation failed for #{dec_num} (attempt {retry + 1}): {error_msg}")
                else:
                    logger.error(f"Content validation failed for #{dec_num} after {max_content_retries + 1} attempts: {error_msg}")
                    decision_data = None

            if not decision_data:
                logger.warning(f"Failed to get valid content for decision #{dec_num} - skipping")
                failed_count += 1
                consecutive_blocks += 1
                if consecutive_blocks >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(f"{MAX_CONSECUTIVE_FAILURES} consecutive failures. Stopping scraping.")
                    break
                continue

            consecutive_blocks = 0

            logger.info(f"Processing decision #{dec_num} with AI...")
            decision_data = process_decision_with_ai(decision_data)
            decision_data = apply_inline_fixes(decision_data)

            qa_warnings = validate_decision_inline(decision_data)
            if qa_warnings:
                for warn in qa_warnings:
                    logger.warning(f"QA [{dec_num}]: {warn}")

            processed_decisions.append(decision_data)
            logger.info(f"Successfully processed decision #{dec_num}")

        except CloudflareBlockedError as e:
            block_cooldown = random.uniform(30.0, 60.0)
            logger.warning(f"Cloudflare block on #{dec_num}: {e}. Cooling down {block_cooldown:.0f}s")
            time.sleep(block_cooldown)
            failed_count += 1
            consecutive_blocks += 1
            if consecutive_blocks >= MAX_CONSECUTIVE_FAILURES:
                logger.error(f"{MAX_CONSECUTIVE_FAILURES} consecutive Cloudflare blocks. Stopping.")
                break
            continue

        except Exception as e:
            logger.error(f"Failed to process decision #{dec_num}: {e}")
            failed_count += 1
            consecutive_blocks += 1
            if consecutive_blocks >= MAX_CONSECUTIVE_FAILURES:
                logger.error(f"{MAX_CONSECUTIVE_FAILURES} consecutive failures. Stopping.")
                break
            continue

    return processed_decisions, failed_count


def _insert_to_database(processed_decisions, existing_keys, total_from_catalog, args, logger):
    """Steps 4-7: Prepare, safety check, approve, and insert to DB."""
    # Step 4: Prepare for database
    logger.info("STEP 4: Preparing data for database insertion...")
    db_ready_decisions = prepare_for_database(processed_decisions)

    # Step 5: Safety duplicate check
    logger.info("STEP 5: Safety duplicate check before insertion...")
    decision_keys = [d['decision_key'] for d in db_ready_decisions]
    final_existing = check_existing_decision_keys(decision_keys)

    new_decisions = [d for d in db_ready_decisions if d['decision_key'] not in final_existing]

    if final_existing:
        logger.info(f"Found {len(final_existing)} decisions inserted since filtering (race condition safety)")

    if not new_decisions:
        logger.info("All processed decisions already exist in database.")
        print("All decisions are already in database. No new data to insert.")
        return True

    logger.info(f"Found {len(new_decisions)} new decisions to insert")

    # Step 6: User approval
    if not args.no_approval:
        logger.info("STEP 6: Getting user approval...")
        if not get_user_approval(new_decisions, None):
            logger.info("User declined. Sync cancelled.")
            print("Sync cancelled by user.")
            return False
    else:
        logger.info("STEP 6: Auto-approval enabled")

    # Step 7: Insert
    logger.info("STEP 7: Inserting decisions into database...")
    inserted_count, error_messages = insert_decisions_batch(new_decisions)

    # Report
    logger.info("=" * 80)
    logger.info("FINAL SYNC SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Entries from catalog: {total_from_catalog}")
    logger.info(f"Decisions processed: {len(processed_decisions)}")
    logger.info(f"New decisions found: {len(new_decisions)}")
    logger.info(f"Duplicates skipped: {len(existing_keys)}")
    logger.info(f"Successfully inserted: {inserted_count}")
    logger.info(f"Failed insertions: {len(error_messages)}")

    if error_messages:
        logger.error("Insertion errors:")
        for error in error_messages:
            logger.error(f"  - {error}")

    logger.info("=" * 80)
    logger.info("DATABASE SYNC COMPLETED")
    logger.info("=" * 80)

    if inserted_count > 0:
        print(f"Successfully synced {inserted_count} new decisions to database!")

    if error_messages:
        print(f"{len(error_messages)} insertions failed. Check logs for details.")
        return False

    print("Database sync completed successfully!")
    return True


def _run_api_sync(args, logger):
    """Run the full sync pipeline using API mode (no Chrome)."""
    extract_catalog_via_api, _ = _import_api_modules()

    # Step 1: Fetch catalog via API
    logger.info("STEP 1: Fetching catalog entries via API (no Chrome)...")

    if args.max_decisions is None:
        batch_size = 100
        logger.info(f"Unlimited mode: Fetching {batch_size} entries")
    else:
        batch_size = args.max_decisions * 2

    decision_entries = extract_catalog_via_api(max_decisions=batch_size)

    if not decision_entries:
        logger.warning("No decision entries found from catalog API")
        print("No entries to process. Sync completed.")
        return True

    total_from_catalog = len(decision_entries)
    logger.info(f"Found {total_from_catalog} decision entries")

    # Step 2: Filter to new entries
    new_entries, existing_keys = _filter_new_entries(decision_entries, logger, args.max_decisions)

    if not new_entries:
        logger.info("No new decisions found. Database is up to date.")
        print("No new decisions found. Database is up to date.")
        return True

    # Step 3: Process decisions via API
    processed_decisions, failed_count = _process_decisions_api(new_entries, logger)

    logger.info(f"Completed processing: {len(processed_decisions)} processed, {failed_count} failed")

    if not processed_decisions:
        logger.info("No decisions were successfully processed.")
        print("No decisions were successfully processed. Check logs for errors.")
        return False

    # Steps 4-7: DB insertion
    return _insert_to_database(processed_decisions, existing_keys, total_from_catalog, args, logger)


def _run_selenium_sync(args, logger):
    """Run the full sync pipeline using Selenium (legacy mode)."""
    extract_decision_urls_from_catalog_selenium, _, SeleniumWebDriver, _ = _import_selenium_modules()

    headless_mode = not args.no_headless
    logger.info(f"Opening shared Chrome session for scraping... (headless={headless_mode})")

    with SeleniumWebDriver(headless=headless_mode) as swd:
        # Step 1: Extract catalog entries
        logger.info("STEP 1: Extracting catalog entries via Selenium...")

        if args.max_decisions is None:
            batch_size = 100
            logger.info(f"Unlimited mode: Fetching {batch_size} entries")
            decision_entries = extract_decision_urls_from_catalog_selenium(max_decisions=batch_size, swd=swd)
        else:
            decision_entries = extract_decision_urls_from_catalog_selenium(
                max_decisions=args.max_decisions * 2, swd=swd
            )

        if not decision_entries:
            logger.warning("No decision entries found")
            print("No entries to process. Sync completed.")
            return True

        total_from_catalog = len(decision_entries)
        logger.info(f"Found {total_from_catalog} decision entries")

        # Step 2: Filter to new entries
        new_entries, existing_keys = _filter_new_entries(decision_entries, logger, args.max_decisions)

        if not new_entries:
            logger.info("No new decisions found. Database is up to date.")
            print("No new decisions found. Database is up to date.")
            return True

        # Step 3: Process decisions via Selenium
        processed_decisions, failed_count = _process_decisions_selenium(new_entries, swd, logger)

    # Chrome session closed
    logger.info("Chrome session closed")
    logger.info(f"Completed processing: {len(processed_decisions)} processed, {failed_count} failed")

    if not processed_decisions:
        logger.info("No decisions were successfully processed.")
        print("No decisions were successfully processed. Check logs for errors.")
        return False

    # Steps 4-7: DB insertion
    return _insert_to_database(processed_decisions, existing_keys, total_from_catalog, args, logger)


def main():
    parser = argparse.ArgumentParser(
        description='Sync Israeli Government Decisions with Supabase Database'
    )
    parser.add_argument('--max-decisions', type=int, default=None,
                        help='Maximum number of new decisions to process (default: unlimited)')
    parser.add_argument('--unlimited', action='store_true',
                        help='Process all new decisions not yet in database (overrides --max-decisions)')
    parser.add_argument('--no-approval', action='store_true',
                        help='Skip user approval step (auto-approve)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--use-api', action='store_true',
                        help='Use API-only mode (no Chrome/Selenium, default for daily sync)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Run Chrome in visible mode (Selenium mode only)')
    parser.add_argument('--manifest', type=str, default=None,
                        help='Load entries from manifest JSON file instead of catalog API')
    parser.add_argument('--local-only', action='store_true',
                        help='Save processed decisions to local JSON file instead of database insertion')

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    if args.unlimited:
        args.max_decisions = None

    mode = "API" if args.use_api else "Selenium"
    limit = "unlimited" if args.max_decisions is None else str(args.max_decisions)

    print(f"Starting {mode} database sync ({limit} mode)...")
    if args.no_approval:
        print("Auto-approval enabled")

    logger.info("=" * 80)
    logger.info(f"STARTING DATABASE SYNC ({mode} MODE)")
    logger.info("=" * 80)
    logger.info(f"Mode: {mode}")
    logger.info(f"Max decisions: {limit}")
    logger.info(f"Auto-approve: {args.no_approval}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("=" * 80)

    try:
        # Step 0: Validate Gemini API key
        if not _validate_gemini_key(logger):
            return False

        if args.use_api:
            return _run_api_sync(args, logger)
        else:
            return _run_selenium_sync(args, logger)

    except Exception as e:
        logger.error(f"Sync process failed: {e}")
        print(f"Sync failed: {e}")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nSync interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
