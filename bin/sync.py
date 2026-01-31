#!/usr/bin/env python3
"""
Selenium-based database sync script for Israeli Government Decisions.
This script extracts decisions using Selenium (for JavaScript-heavy websites) 
and syncs them with the Supabase database.
"""

import argparse
import logging
import os
import sys

# Add src to Python path for package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.scrapers.catalog import extract_decision_urls_from_catalog_selenium
from gov_scraper.scrapers.decision import scrape_decision_with_url_recovery
from gov_scraper.processors.ai import process_decision_with_ai
from gov_scraper.processors.incremental import prepare_for_database
from gov_scraper.db.dal import insert_decisions_batch, check_existing_decision_keys
from gov_scraper.processors.approval import get_user_approval
from gov_scraper.processors.qa import validate_decision_inline, validate_scraped_content, apply_inline_fixes
from gov_scraper.config import LOG_DIR, LOG_FILE, GOVERNMENT_NUMBER

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

def main():
    parser = argparse.ArgumentParser(
        description='Sync Israeli Government Decisions with Supabase Database (Selenium-based)'
    )
    parser.add_argument('--max-decisions', type=int, default=None,
                        help='Maximum number of new decisions to process (default: unlimited)')
    parser.add_argument('--unlimited', action='store_true',
                        help='Process all new decisions not yet in database (overrides --max-decisions)')
    parser.add_argument('--no-approval', action='store_true',
                        help='Skip user approval step (auto-approve)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--safety-mode', type=str, default='regular',
                        choices=['regular', 'extra-safe'],
                        help='Deprecated: kept for backward compatibility. Filtering is now key-based (all entries checked against DB).')

    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Handle unlimited mode
    if args.unlimited:
        args.max_decisions = None
        
    if args.max_decisions is None:
        print("🚀 Starting Selenium-based database sync (unlimited mode)...")
        print("📊 Will process all new decisions not yet in database")
    else:
        print(f"🚀 Starting Selenium-based database sync for up to {args.max_decisions} decisions...")

    if args.no_approval:
        print("⚡ Auto-approval enabled - no user confirmation required")

    logger.info("=" * 80)
    logger.info("🚀 STARTING SELENIUM DATABASE SYNC ORCHESTRATOR")
    logger.info("=" * 80)
    logger.info(f"Max decisions to process: {'Unlimited' if args.max_decisions is None else args.max_decisions}")
    logger.info(f"AI processing: Enabled (required)")
    logger.info(f"User approval required: {'No' if args.no_approval else 'Yes'}")
    logger.info(f"Filtering: Key-based DB check (processes all entries not in database)")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("=" * 80)

    try:
        # Step 0: Validate Gemini API key with a test request
        logger.info("🔑 STEP 0: Validating Gemini API key...")
        try:
            from gov_scraper.processors.ai import gemini_client
            from gov_scraper.config import GEMINI_MODEL
            if not gemini_client:
                raise ValueError("Gemini client not initialized - API key is missing or invalid")

            # Make a minimal test request to validate the API key
            test_response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents="test",
                config={"max_output_tokens": 5}
            )
            logger.info("✅ Gemini API key validated successfully")
        except Exception as e:
            logger.error(f"❌ Gemini API key validation failed: {e}")
            print(f"\n❌ ERROR: Gemini API key is invalid or not working!")
            print(f"Details: {e}")
            print("\nPlease check your .env file and ensure GEMINI_API_KEY is set correctly.")
            print("Get your API key from: https://aistudio.google.com/app/apikey\n")
            return False

        # Step 1: Extract decision entries using Selenium + catalog API
        logger.info("🔍 STEP 1: Extracting decision entries from catalog API using Selenium...")

        if args.max_decisions is None:
            large_batch_size = 100
            logger.info(f"🔄 Unlimited mode: Fetching {large_batch_size} entries to ensure complete coverage")
            logger.info("⏱️  Large batch loading may take 30-60 seconds - please wait...")
            decision_entries = extract_decision_urls_from_catalog_selenium(max_decisions=large_batch_size)
        else:
            decision_entries = extract_decision_urls_from_catalog_selenium(
                max_decisions=args.max_decisions * 2
            )

        if not decision_entries:
            logger.warning("⚠️  No decision entries found")
            print("🏁 No entries to process. Sync completed.")
            return True

        total_from_catalog = len(decision_entries)
        logger.info(f"✅ Found {total_from_catalog} decision entries")

        # Step 2: Filter to new entries by checking which already exist in database
        logger.info("🔍 STEP 2: Checking which entries already exist in database...")

        candidate_keys = []
        key_to_entry = {}
        for entry in decision_entries:
            dec_num = entry.get('decision_number', '')
            if dec_num:
                key = f"{GOVERNMENT_NUMBER}_{dec_num}"
                candidate_keys.append(key)
                key_to_entry[key] = entry

        existing_keys = check_existing_decision_keys(candidate_keys)
        logger.info(f"📊 Found {len(existing_keys)} entries already in database out of {len(candidate_keys)} candidates")

        new_entries = [key_to_entry[k] for k in candidate_keys if k not in existing_keys]
        new_entries.sort(key=lambda e: (e.get('decision_date', ''), e.get('decision_number', '')))
        logger.info(f"📝 Identified {len(new_entries)} new entries to process")

        if not new_entries:
            logger.info("🏁 No new decisions found. Database is up to date.")
            print("✅ No new decisions found. Database is up to date.")
            return True

        # Step 3: Process decisions - scrape content and run AI
        logger.info("📄 STEP 3: Processing new decisions...")
        processed_decisions = []
        failed_count = 0

        if args.max_decisions is not None:
            entries_to_process = new_entries[:args.max_decisions]
        else:
            entries_to_process = new_entries

        logger.info(f"📊 Will process {len(entries_to_process)} new decisions")

        for i, entry in enumerate(entries_to_process, 1):
            dec_num = entry.get('decision_number', '?')
            dec_url = entry.get('url', '')
            logger.info(f"Processing decision {i}/{len(entries_to_process)}: #{dec_num} {dec_url}")

            try:
                # Scrape content with retry on bad content (Cloudflare, short, no Hebrew)
                decision_data = None
                max_content_retries = 2

                for retry in range(max_content_retries + 1):
                    wait_time = 15 + (retry * 10)  # 15s, 25s, 35s
                    decision_data = scrape_decision_with_url_recovery(entry, wait_time=wait_time)

                    if not decision_data:
                        break  # Scraping itself failed — no point retrying content validation

                    # Pre-AI content validation
                    is_valid, error_msg = validate_scraped_content(decision_data)
                    if is_valid:
                        break

                    if retry < max_content_retries:
                        logger.warning(f"Content validation failed for #{dec_num} (attempt {retry + 1}): {error_msg} — retrying with {wait_time + 10}s wait")
                    else:
                        logger.error(f"Content validation failed for #{dec_num} after {max_content_retries + 1} attempts: {error_msg} — skipping")
                        decision_data = None

                if not decision_data:
                    logger.warning(f"Failed to get valid content for decision #{dec_num} from {dec_url} - skipping")
                    failed_count += 1
                    continue

                # Process with AI (required)
                logger.info(f"🤖 Processing decision #{dec_num} with AI...")
                decision_data = process_decision_with_ai(decision_data)

                # Post-AI algorithmic fixes ($0 cost)
                decision_data = apply_inline_fixes(decision_data)

                # QA inline validation (warnings only, does not block)
                qa_warnings = validate_decision_inline(decision_data)
                if qa_warnings:
                    for warn in qa_warnings:
                        logger.warning(f"⚠️  QA [{dec_num}]: {warn}")

                processed_decisions.append(decision_data)
                logger.info(f"✅ Successfully processed decision #{dec_num}")

            except Exception as e:
                logger.error(f"Failed to process decision #{dec_num}: {e}")
                failed_count += 1
                continue

        logger.info(f"📊 Completed processing: {len(processed_decisions)} decisions processed, {failed_count} failed")

        logger.info("=" * 60)
        logger.info("📊 FILTERING STATISTICS:")
        logger.info(f"  Entries from catalog API: {total_from_catalog}")
        logger.info(f"  Already in database: {len(existing_keys)}")
        logger.info(f"  New entries identified: {len(new_entries)}")
        logger.info(f"  Entries processed: {len(entries_to_process)}")
        logger.info(f"  Decisions scraped + AI processed: {len(processed_decisions)}")
        logger.info(f"  Failed: {failed_count}")
        logger.info("=" * 60)

        if not processed_decisions:
            logger.info("🏁 No decisions were successfully processed.")
            print("⚠️  No decisions were successfully processed. Check logs for errors.")
            return False

        logger.info(f"📊 Processed {len(processed_decisions)} decisions successfully ({failed_count} failed)")

        # Step 4: Prepare data for database
        logger.info("🔄 STEP 4: Preparing data for database insertion...")
        db_ready_decisions = prepare_for_database(processed_decisions)

        # Step 5: Safety check for duplicates (race condition protection)
        logger.info("🔍 STEP 5: Safety duplicate check before insertion...")
        decision_keys = [d['decision_key'] for d in db_ready_decisions]
        final_existing = check_existing_decision_keys(decision_keys)

        new_decisions = [d for d in db_ready_decisions if d['decision_key'] not in final_existing]

        if final_existing:
            logger.info(f"⏭️  Found {len(final_existing)} decisions inserted since filtering (race condition safety)")

        if not new_decisions:
            logger.info("🏁 All processed decisions already exist in database.")
            print("✅ All decisions are already in database. No new data to insert.")
            return True

        logger.info(f"📝 Found {len(new_decisions)} new decisions to insert")

        # Step 6: User approval (unless disabled)
        if not args.no_approval:
            logger.info("👤 STEP 6: Getting user approval...")
            if not get_user_approval(new_decisions, None):
                logger.info("❌ User declined to proceed. Sync cancelled.")
                print("❌ Sync cancelled by user.")
                return False
        else:
            logger.info("⚡ STEP 6: Auto-approval enabled - proceeding without confirmation")

        # Step 7: Insert into database
        logger.info("💾 STEP 7: Inserting decisions into database...")
        inserted_count, error_messages = insert_decisions_batch(new_decisions)
        
        # Report results
        logger.info("=" * 80)
        logger.info("📊 FINAL SYNC SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Entries from catalog: {total_from_catalog}")
        logger.info(f"Decisions processed: {len(processed_decisions)}")
        logger.info(f"New decisions found: {len(new_decisions)}")
        logger.info(f"Duplicates skipped: {len(existing_keys)}")
        logger.info(f"AI processed: {len(processed_decisions)}")
        logger.info(f"Successfully inserted: {inserted_count}")
        logger.info(f"Failed insertions: {len(error_messages)}")
        
        if error_messages:
            logger.error("❌ Insertion errors:")
            for error in error_messages:
                logger.error(f"  - {error}")
        
        logger.info("=" * 80)
        logger.info("🏁 SELENIUM DATABASE SYNC COMPLETED")
        logger.info("=" * 80)
        
        # Final status
        if inserted_count > 0:
            print(f"🎉 Successfully synced {inserted_count} new decisions to database!")
        
        if error_messages:
            print(f"⚠️  {len(error_messages)} insertions failed. Check logs for details.")
            return False
        
        print("✅ Database sync completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"💥 Sync process failed: {e}")
        print(f"❌ Sync failed: {e}")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Sync interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)