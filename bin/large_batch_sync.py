#!/usr/bin/env python3
"""
LARGE BATCH SYNC - Optimized for 350+ decisions
This script is specifically designed for processing large gaps in the database.
Features:
- No timeout whatsoever
- Optimized batch processing  
- Progress tracking with ETA
- Robust error recovery
- Comprehensive logging
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

# Add src to Python path for package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.scrapers.catalog import extract_decision_urls_from_catalog_selenium
from gov_scraper.scrapers.decision import scrape_decision_page_selenium
from gov_scraper.processors.ai import process_decision_with_ai
from gov_scraper.processors.incremental import get_scraping_baseline, should_process_decision, prepare_for_database
from gov_scraper.db.dal import insert_decisions_batch, check_existing_decision_keys
from gov_scraper.config import LOG_DIR, LOG_FILE

def setup_logging():
    """Set up comprehensive logging for large batch processing."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f'large_batch_sync_{timestamp}.log')
    
    # Set up logging with both file and console output
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return log_file

def estimate_completion_time(processed: int, total_estimated: int, start_time: datetime, with_ai: bool = False):
    """Estimate completion time based on current progress."""
    if processed == 0:
        return "Calculating..."
    
    elapsed = datetime.now() - start_time
    avg_time_per_decision = elapsed.total_seconds() / processed
    
    # Adjust estimate based on AI processing
    if with_ai:
        avg_time_per_decision *= 1.5  # AI adds ~50% more time
    
    remaining_decisions = total_estimated - processed
    estimated_remaining_seconds = remaining_decisions * avg_time_per_decision
    
    estimated_completion = datetime.now() + timedelta(seconds=estimated_remaining_seconds)
    
    return {
        'eta': estimated_completion.strftime('%H:%M:%S'),
        'remaining_time': str(timedelta(seconds=int(estimated_remaining_seconds))),
        'avg_per_decision': f"{avg_time_per_decision:.1f}s"
    }

def main():
    parser = argparse.ArgumentParser(
        description='Large Batch Sync - Optimized for 350+ decisions with no timeout'
    )
    parser.add_argument('--with-ai', action='store_true',
                        help='Include AI processing (slower but complete)')
    parser.add_argument('--batch-size', type=int, default=500,
                        help='Number of URLs to fetch per batch (default: 500 for comprehensive coverage)')
    
    args = parser.parse_args()
    
    # Setup logging
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    
    start_time = datetime.now()
    
    print("🌙 LARGE BATCH SYNC - NO TIMEOUT")
    print("=" * 60)
    print(f"🕐 Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Log file: {log_file}")
    print(f"🤖 AI processing: {'Enabled' if args.with_ai else 'Disabled (faster)'}")
    print(f"📦 Batch size: {args.batch_size} URLs per fetch")
    print("✅ NO TIMEOUT - Will run until completion")
    print("=" * 60)
    
    logger.info("🚀 STARTING LARGE BATCH SYNC")
    logger.info(f"Configuration: AI={args.with_ai}, BatchSize={args.batch_size}")
    
    try:
        # Step 1: Get baseline
        logger.info("📊 Getting database baseline...")
        baseline = get_scraping_baseline()
        
        if baseline:
            baseline_info = f"Decision {baseline.get('decision_number')} ({baseline.get('decision_date')})"
            logger.info(f"✅ Baseline found: {baseline_info}")
            print(f"📊 Database baseline: {baseline_info}")
        else:
            logger.info("ℹ️  No baseline found - will process all decisions")
            print("📊 No baseline found - processing all available decisions")
        
        # Step 2: Start processing with expanding batches
        total_processed = 0
        total_inserted = 0
        batch_number = 1
        all_decisions_processed = []
        
        while True:
            logger.info(f"🔍 BATCH {batch_number}: Fetching {args.batch_size} URLs...")
            print(f"\n🔍 BATCH {batch_number}: Fetching decision URLs...")
            
            # Get decision URLs for this batch
            decision_urls = extract_decision_urls_from_catalog_selenium(
                max_decisions=args.batch_size
            )
            
            if not decision_urls:
                logger.info("✅ No more URLs found - sync complete")
                print("✅ No more decision URLs found - sync complete!")
                break
            
            logger.info(f"📋 Found {len(decision_urls)} URLs in batch {batch_number}")
            print(f"📋 Processing {len(decision_urls)} decisions in this batch...")
            
            # Process each decision in this batch
            batch_processed = []
            baseline_reached = False
            
            for i, url in enumerate(decision_urls, 1):
                logger.info(f"Processing decision {i}/{len(decision_urls)} in batch {batch_number}: {url}")
                
                try:
                    # Scrape decision
                    decision_data = scrape_decision_page_selenium(url)
                    
                    if not decision_data:
                        logger.error(f"Failed to scrape {url}")
                        continue
                    
                    # Check baseline
                    if baseline and not should_process_decision(decision_data, baseline):
                        logger.info(f"🎯 BASELINE REACHED! Decision {decision_data.get('decision_number')} is older than baseline")
                        logger.info("⏹️  Stopping processing - all newer decisions captured")
                        print(f"🎯 Reached baseline! Stopping at decision {decision_data.get('decision_number')}")
                        baseline_reached = True
                        break
                    
                    # Process with AI if requested
                    if args.with_ai:
                        logger.info(f"🤖 Processing decision {decision_data.get('decision_number')} with AI...")
                        decision_data = process_decision_with_ai(decision_data)
                    
                    batch_processed.append(decision_data)
                    total_processed += 1
                    
                    # Progress update every 10 decisions
                    if total_processed % 10 == 0:
                        estimate = estimate_completion_time(total_processed, 350, start_time, args.with_ai)
                        if isinstance(estimate, dict):
                            logger.info(f"📊 Progress: {total_processed} processed | ETA: {estimate['eta']} | Avg: {estimate['avg_per_decision']}/decision")
                            print(f"📊 Progress: {total_processed} decisions | ETA: {estimate['eta']}")
                    
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    continue
            
            # Insert this batch
            if batch_processed:
                logger.info(f"💾 Preparing {len(batch_processed)} decisions for database insertion...")
                
                # Prepare for database
                db_ready = prepare_for_database(batch_processed)
                
                # Check duplicates
                decision_keys = [d['decision_key'] for d in db_ready]
                existing_keys = check_existing_decision_keys(decision_keys)
                new_decisions = [d for d in db_ready if d['decision_key'] not in existing_keys]
                
                if new_decisions:
                    logger.info(f"📝 Inserting {len(new_decisions)} new decisions (skipping {len(existing_keys)} duplicates)")
                    inserted_count, errors = insert_decisions_batch(new_decisions)
                    total_inserted += inserted_count
                    
                    if errors:
                        logger.error(f"❌ {len(errors)} insertion errors occurred")
                    
                    logger.info(f"✅ Batch {batch_number} complete: {inserted_count} inserted")
                    print(f"✅ Batch {batch_number}: {inserted_count} decisions inserted")
                else:
                    logger.info(f"⏭️  Batch {batch_number}: All decisions were duplicates")
                    print(f"⏭️  Batch {batch_number}: All decisions already in database")
                
                all_decisions_processed.extend(batch_processed)
            
            # Stop if baseline reached
            if baseline_reached:
                break
                
            batch_number += 1
            
            # Brief pause between batches to be nice to the server
            time.sleep(2)
        
        # Final summary
        end_time = datetime.now()
        total_time = end_time - start_time
        
        logger.info("=" * 60)
        logger.info("🏁 LARGE BATCH SYNC COMPLETED")
        logger.info("=" * 60)
        logger.info(f"⏱️  Total time: {total_time}")
        logger.info(f"📊 Total processed: {total_processed} decisions")
        logger.info(f"💾 Total inserted: {total_inserted} decisions")
        logger.info(f"📦 Batches processed: {batch_number - 1}")
        logger.info(f"⚡ Average speed: {total_processed / total_time.total_seconds():.2f} decisions/second")
        
        print("\n" + "=" * 60)
        print("🎉 OVERNIGHT SYNC COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"⏱️  Total time: {total_time}")
        print(f"📊 Decisions processed: {total_processed}")
        print(f"💾 New decisions added: {total_inserted}")
        print(f"📝 Detailed logs: {log_file}")
        print("=" * 60)
        print("☀️  Good morning! Your database is now up to date.")
        
        return True
        
    except Exception as e:
        logger.error(f"💥 Sync failed: {e}")
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