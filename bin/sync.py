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
from datetime import datetime

# Add src to Python path for package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.scrapers.catalog import extract_decision_urls_from_catalog_selenium
from gov_scraper.scrapers.decision import scrape_decision_page_selenium, scrape_decision_with_url_recovery
from gov_scraper.processors.ai import process_decision_with_ai
from gov_scraper.processors.incremental import get_scraping_baseline, should_process_decision, prepare_for_database
from gov_scraper.db.dal import insert_decisions_batch, check_existing_decision_keys
from gov_scraper.processors.approval import get_user_approval
from gov_scraper.config import LOG_DIR, LOG_FILE

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
                        help='Maximum number of decisions to process (default: unlimited until baseline)')
    parser.add_argument('--unlimited', action='store_true',
                        help='Process all decisions until reaching database baseline (overrides --max-decisions)')
    parser.add_argument('--no-ai', action='store_true',
                        help='Skip AI processing for faster bulk import')
    parser.add_argument('--no-approval', action='store_true',
                        help='Skip user approval step (auto-approve)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Handle unlimited mode
    if args.unlimited:
        args.max_decisions = None
        
    if args.max_decisions is None:
        print("🚀 Starting Selenium-based database sync with UNLIMITED processing until baseline...")
        print("📊 Will process all decisions until reaching the most recent decision in database")
    else:
        print(f"🚀 Starting Selenium-based database sync for up to {args.max_decisions} decisions...")
    
    if args.no_ai:
        print("⚡ AI processing disabled - faster bulk import mode")
    if args.no_approval:
        print("⚡ Auto-approval enabled - no user confirmation required")
    
    logger.info("=" * 80)
    logger.info("🚀 STARTING SELENIUM DATABASE SYNC ORCHESTRATOR")
    logger.info("=" * 80)
    logger.info(f"Max decisions to process: {'Unlimited (until baseline)' if args.max_decisions is None else args.max_decisions}")
    logger.info(f"AI processing: {'Disabled' if args.no_ai else 'Enabled'}")
    logger.info(f"User approval required: {'No' if args.no_approval else 'Yes'}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("=" * 80)
    
    try:
        # Step 1: Get database baseline for incremental processing
        logger.info("📊 STEP 1: Getting database baseline...")
        baseline = get_scraping_baseline()
        
        if baseline:
            logger.info(f"✅ Baseline found: Decision {baseline.get('decision_number')} ({baseline.get('decision_date')})")
        else:
            logger.info("ℹ️  No baseline found - will process all decisions found")
        
        # Step 2: Extract decision URLs using Selenium
        logger.info("🔍 STEP 2: Extracting decision URLs from catalog using Selenium...")
        
        if args.max_decisions is None:
            # Unlimited mode - use large batch size for comprehensive coverage
            large_batch_size = 500
            logger.info(f"🔄 Unlimited mode: Fetching {large_batch_size} URLs to ensure complete coverage")
            logger.info("⏱️  Large batch loading may take 30-60 seconds - please wait...")
            decision_urls = extract_decision_urls_from_catalog_selenium(max_decisions=large_batch_size)
        else:
            # Limited mode - get extra URLs for smart filtering
            decision_urls = extract_decision_urls_from_catalog_selenium(
                max_decisions=args.max_decisions * 2  # Get extra URLs for smart filtering
            )
        
        if not decision_urls:
            logger.warning("⚠️  No decision URLs found")
            print("🏁 No URLs to process. Sync completed.")
            return True
        
        logger.info(f"✅ Found {len(decision_urls)} decision URLs")
        
        # Step 3: Filter URLs by baseline and sort for ascending processing
        logger.info("📄 STEP 3: Filtering URLs by baseline and preparing for ascending processing...")
        
        if baseline:
            # Filter URLs to only those newer than baseline
            filtered_urls = []
            for url in decision_urls:
                # Quick extraction to check if this URL should be processed
                from gov_scraper.scrapers.decision import extract_decision_number_from_url
                decision_number = extract_decision_number_from_url(url)
                if decision_number:
                    # For URL filtering, we'll be more permissive and let the actual scraping determine dates
                    # We'll filter based on decision number vs baseline number as a rough filter
                    try:
                        if int(decision_number) > int(baseline.get('decision_number', '0')):
                            filtered_urls.append(url)
                    except (ValueError, TypeError):
                        # If we can't compare numbers, include the URL to be safe
                        filtered_urls.append(url)
            
            logger.info(f"📊 Filtered {len(decision_urls)} URLs to {len(filtered_urls)} URLs newer than baseline")
            decision_urls = filtered_urls
        
        # Sort URLs in ascending order (oldest first) for processing from baseline forward
        def extract_decision_info_for_ascending_sort(url):
            """Extract decision info for ascending sort (oldest first)."""
            import re
            match = re.search(r'/dec(\d+)([a-z]?)-(\d{4})([a-z]?)', url)
            if match:
                decision_num = int(match.group(1))
                prefix_suffix = match.group(2) or ""
                year = int(match.group(3))
                postfix_suffix = match.group(4) or ""
                
                # Return positive values for ascending order (oldest first)
                suffix_order = ord(prefix_suffix) if prefix_suffix else 0
                postfix_order = ord(postfix_suffix) if postfix_suffix else 0
                
                return (year, decision_num, suffix_order, postfix_order)
            return (9999, 9999, 999, 999)  # Put unparseable URLs at the end
        
        decision_urls.sort(key=extract_decision_info_for_ascending_sort)
        logger.info("🔄 Sorted URLs in ascending order (processing from baseline forward)")
        
        # Step 4: Process decisions and extract data
        logger.info("📄 STEP 4: Processing decisions in ascending order...")
        processed_decisions = []
        failed_count = 0
        
        # Determine which URLs to process
        if args.max_decisions is None:
            urls_to_process = decision_urls  # Process all URLs in unlimited mode
            max_desc = "all filtered URLs from baseline forward"
        else:
            urls_to_process = decision_urls[:args.max_decisions]
            max_desc = f"{min(len(decision_urls), args.max_decisions)}"
        
        logger.info(f"📊 Will process {max_desc}")
        
        for i, url in enumerate(urls_to_process, 1):
            logger.info(f"Processing decision {i}/{len(urls_to_process) if args.max_decisions else '?'}: {url}")
            
            try:
                # Use URL recovery for robust scraping
                decision_data = scrape_decision_with_url_recovery(url)
                
                if not decision_data:
                    logger.warning(f"Failed to scrape decision from {url} even with URL recovery - skipping")
                    failed_count += 1
                    continue
                
                # Process with AI if enabled
                if not args.no_ai:
                    logger.info(f"🤖 Processing decision {decision_data.get('decision_number')} with AI...")
                    decision_data = process_decision_with_ai(decision_data)
                
                processed_decisions.append(decision_data)
                logger.info(f"✅ Successfully processed decision {decision_data.get('decision_number')}")
                
            except Exception as e:
                logger.error(f"Failed to process decision from {url}: {e}")
                failed_count += 1
                continue
        
        # Log processing results
        logger.info(f"📊 Completed processing: {len(processed_decisions)} decisions processed, {failed_count} failed/skipped")
        
        if not processed_decisions:
            logger.info("🏁 No new decisions to process after filtering. Sync completed.")
            print("✅ No new decisions found. Database is up to date.")
            return True
        
        logger.info(f"📊 Processed {len(processed_decisions)} decisions successfully ({failed_count} failed/skipped)")
        
        # Step 5: Prepare data for database
        logger.info("🔄 STEP 5: Preparing data for database insertion...")
        db_ready_decisions = prepare_for_database(processed_decisions)
        
        # Step 6: Check for duplicates
        logger.info("🔍 STEP 6: Checking for existing decisions...")
        decision_keys = [d['decision_key'] for d in db_ready_decisions]
        existing_keys = check_existing_decision_keys(decision_keys)
        
        # Filter out duplicates
        new_decisions = [d for d in db_ready_decisions if d['decision_key'] not in existing_keys]
        
        if existing_keys:
            logger.info(f"⏭️  Found {len(existing_keys)} duplicate decisions (will skip)")
            
        if not new_decisions:
            logger.info("🏁 All processed decisions already exist in database.")
            print("✅ All decisions are already in database. No new data to insert.")
            return True
        
        logger.info(f"📝 Found {len(new_decisions)} new decisions to insert")
        
        # Step 7: User approval (unless disabled)
        if not args.no_approval:
            logger.info("👤 STEP 7: Getting user approval...")
            if not get_user_approval(new_decisions, baseline):
                logger.info("❌ User declined to proceed. Sync cancelled.")
                print("❌ Sync cancelled by user.")
                return False
        else:
            logger.info("⚡ STEP 7: Auto-approval enabled - proceeding without confirmation")
        
        # Step 8: Insert into database
        logger.info("💾 STEP 8: Inserting decisions into database...")
        inserted_count, error_messages = insert_decisions_batch(new_decisions)
        
        # Report results
        logger.info("=" * 80)
        logger.info("📊 FINAL SYNC SUMMARY")
        logger.info("=" * 80)
        logger.info(f"URLs scraped: {len(decision_urls)}")
        logger.info(f"Decisions processed: {len(processed_decisions)}")
        logger.info(f"New decisions found: {len(new_decisions)}")
        logger.info(f"Duplicates skipped: {len(existing_keys)}")
        logger.info(f"AI processed: {len(processed_decisions) if not args.no_ai else 0}")
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