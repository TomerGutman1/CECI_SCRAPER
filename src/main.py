"""Main script to orchestrate the Israeli Government decisions scraping process."""

import logging
import os
import sys
from datetime import datetime

# Add the src directory to Python path
sys.path.append(os.path.dirname(__file__))

from catalog_scraper import extract_decision_urls_from_catalog
from decision_scraper import scrape_decision_page
from ai_processor import process_decision_with_ai
from data_manager import save_decisions_to_csv, validate_decision_data
from config import LOG_DIR, LOG_FILE, OPENAI_API_KEY

# Set up logging
def setup_logging():
    """Set up logging configuration."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    log_path = os.path.join(LOG_DIR, LOG_FILE)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def main(max_decisions: int = 5, use_ai: bool = True):
    """
    Main function to scrape government decisions.
    
    Args:
        max_decisions: Maximum number of decisions to scrape
        use_ai: Whether to use AI processing for summaries and tags
    """
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Starting Israeli Government Decisions Scraper")
    logger.info(f"Target: {max_decisions} decisions")
    logger.info(f"AI Processing: {'Enabled' if use_ai and OPENAI_API_KEY else 'Disabled'}")
    logger.info("=" * 60)
    
    all_decisions_data = []
    
    try:
        # Step 1: Extract decision URLs from catalog
        logger.info("Step 1: Extracting decision URLs from catalog...")
        decision_urls = extract_decision_urls_from_catalog(max_decisions)
        
        if not decision_urls:
            logger.error("No decision URLs found. Exiting.")
            return
        
        logger.info(f"Found {len(decision_urls)} decision URLs to process")
        
        # Step 2: Process each decision
        for i, url in enumerate(decision_urls, 1):
            logger.info(f"\nStep 2.{i}: Processing decision {i}/{len(decision_urls)}")
            logger.info(f"URL: {url}")
            
            try:
                # Scrape the decision page
                decision_data = scrape_decision_page(url)
                
                # Validate the scraped data
                validation_issues = validate_decision_data(decision_data)
                if validation_issues:
                    logger.warning(f"Validation issues for decision {i}: {validation_issues}")
                
                # Process with AI if enabled and API key is available
                if use_ai and OPENAI_API_KEY:
                    logger.info(f"Processing decision {i} with AI...")
                    decision_data = process_decision_with_ai(decision_data)
                else:
                    logger.info(f"Skipping AI processing for decision {i}")
                    # Fill AI fields with empty values
                    ai_fields = ['summary', 'operativity', 'tags_policy_area', 
                               'tags_government_body', 'tags_location', 'all_tags']
                    for field in ai_fields:
                        if field not in decision_data:
                            decision_data[field] = ''
                
                all_decisions_data.append(decision_data)
                logger.info(f"Successfully processed decision {i}")
                
            except Exception as e:
                logger.error(f"Failed to process decision {i} ({url}): {e}")
                continue
        
        # Step 3: Save to CSV
        logger.info(f"\nStep 3: Saving {len(all_decisions_data)} decisions to CSV...")
        
        if all_decisions_data:
            output_file = save_decisions_to_csv(all_decisions_data)
            logger.info(f"✅ Successfully saved data to: {output_file}")
            
            # Print summary
            logger.info("\n" + "=" * 60)
            logger.info("SCRAPING SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Total URLs found: {len(decision_urls)}")
            logger.info(f"Successfully processed: {len(all_decisions_data)}")
            logger.info(f"Failed: {len(decision_urls) - len(all_decisions_data)}")
            logger.info(f"Output file: {output_file}")
            
            # Show sample data
            if all_decisions_data:
                sample = all_decisions_data[0]
                logger.info(f"\nSample decision:")
                logger.info(f"  Number: {sample.get('decision_number', 'N/A')}")
                logger.info(f"  Date: {sample.get('decision_date', 'N/A')}")
                logger.info(f"  Title: {sample.get('decision_title', 'N/A')[:50]}...")
                logger.info(f"  Content length: {len(sample.get('decision_content', ''))} chars")
                logger.info(f"  Has summary: {'Yes' if sample.get('summary') else 'No'}")
            
        else:
            logger.error("No decisions were successfully processed")
        
    except Exception as e:
        logger.error(f"Fatal error in main process: {e}")
        raise
    
    logger.info("=" * 60)
    logger.info("Scraping process completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Check if OpenAI API key is set
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not found in environment variables.")
        print("   AI processing will be skipped. To enable AI features:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your OpenAI API key to the .env file")
        print("   3. Run the script again")
        print()
        
        response = input("Continue without AI processing? (y/n): ").lower()
        if response != 'y':
            print("Exiting...")
            sys.exit(1)
    
    # Parse command line arguments (simple version)
    max_decisions = 5
    if len(sys.argv) > 1:
        try:
            max_decisions = int(sys.argv[1])
        except ValueError:
            print(f"Invalid number of decisions: {sys.argv[1]}")
            sys.exit(1)
    
    print(f"Starting scraper for {max_decisions} decisions...")
    
    try:
        main(max_decisions=max_decisions, use_ai=bool(OPENAI_API_KEY))
    except KeyboardInterrupt:
        print("\n❌ Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Scraping failed: {e}")
        sys.exit(1)