"""Main script using Selenium to scrape real Israeli Government decisions."""

import logging
import os
import sys
from datetime import datetime

# Add the src directory to Python path
sys.path.append(os.path.dirname(__file__))

from catalog_scraper_selenium import extract_decision_urls_from_catalog_selenium
from decision_scraper_selenium import scrape_decision_page_selenium
from ai_processor import process_decision_with_ai
from data_manager import save_decisions_to_csv, validate_decision_data
from config import LOG_DIR, LOG_FILE, GEMINI_API_KEY

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


def main_selenium(max_decisions: int = 5, use_ai: bool = True):
    """
    Main function to scrape government decisions using Selenium.
    
    Args:
        max_decisions: Maximum number of decisions to scrape
        use_ai: Whether to use AI processing for summaries and tags
    """
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Starting Israeli Government Decisions Scraper (SELENIUM)")
    logger.info(f"Target: {max_decisions} decisions")
    logger.info(f"AI Processing: {'Enabled' if use_ai and GEMINI_API_KEY else 'Disabled'}")
    logger.info("=" * 60)
    
    all_decisions_data = []
    
    try:
        # Step 1: Extract decision URLs from catalog using Selenium
        logger.info("Step 1: Extracting decision URLs from catalog using Selenium...")
        decision_urls = extract_decision_urls_from_catalog_selenium(max_decisions)
        
        if not decision_urls:
            logger.error("No decision URLs found. Exiting.")
            return
        
        logger.info(f"Found {len(decision_urls)} decision URLs to process")
        
        # Step 2: Process each decision using Selenium
        for i, url in enumerate(decision_urls, 1):
            logger.info(f"\nStep 2.{i}: Processing decision {i}/{len(decision_urls)}")
            logger.info(f"URL: {url}")
            
            try:
                # Scrape the decision page using Selenium
                decision_data = scrape_decision_page_selenium(url)
                
                # Validate the scraped data
                validation_issues = validate_decision_data(decision_data)
                if validation_issues:
                    logger.warning(f"Validation issues for decision {i}: {validation_issues}")
                
                # Process with AI if enabled and API key is available
                if use_ai and GEMINI_API_KEY:
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
                
                # Show preview of what we got
                content_preview = decision_data.get('decision_content', '')[:200]
                logger.info(f"Content preview: {content_preview}...")
                
            except Exception as e:
                logger.error(f"Failed to process decision {i} ({url}): {e}")
                continue
        
        # Step 3: Save to CSV
        logger.info(f"\nStep 3: Saving {len(all_decisions_data)} decisions to CSV...")
        
        if all_decisions_data:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = save_decisions_to_csv(all_decisions_data, f"scraped_decisions_{timestamp}.csv")
            logger.info(f"✅ Successfully saved data to: {output_file}")
            
            # Print summary
            logger.info("\n" + "=" * 60)
            logger.info("SELENIUM SCRAPING SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Total URLs found: {len(decision_urls)}")
            logger.info(f"Successfully processed: {len(all_decisions_data)}")
            logger.info(f"Failed: {len(decision_urls) - len(all_decisions_data)}")
            logger.info(f"Output file: {output_file}")
            
            # Show sample data
            if all_decisions_data:
                sample = all_decisions_data[0]
                logger.info(f"\nSample decision (Real Data!):")
                logger.info(f"  Number: {sample.get('decision_number', 'N/A')}")
                logger.info(f"  Date: {sample.get('decision_date', 'N/A')[:50]}...")
                logger.info(f"  Title: {sample.get('decision_title', 'N/A')[:100]}...")
                logger.info(f"  Content length: {len(sample.get('decision_content', ''))} chars")
                logger.info(f"  Has Hebrew: {any(char > '\\u0590' for char in sample.get('decision_content', ''))}")
                logger.info(f"  Has AI summary: {'Yes' if sample.get('summary') else 'No'}")
            
        else:
            logger.error("No decisions were successfully processed")
        
    except Exception as e:
        logger.error(f"Fatal error in main process: {e}")
        raise
    
    logger.info("=" * 60)
    logger.info("Selenium scraping process completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Check if Gemini API key is set
    ai_available = bool(GEMINI_API_KEY)
    if not ai_available:
        print("⚠️  Warning: GEMINI_API_KEY not found in environment variables.")
        print("   AI processing will be skipped. To enable AI features:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your Gemini API key to the .env file")
        print("   3. Run the script again")
        print()
    
    # Parse command line arguments (simple version)
    max_decisions = 5
    if len(sys.argv) > 1:
        try:
            max_decisions = int(sys.argv[1])
        except ValueError:
            print(f"Invalid number of decisions: {sys.argv[1]}")
            sys.exit(1)
    
    print(f"🚀 Starting Selenium-based scraper for {max_decisions} decisions...")
    print(f"🤖 AI processing: {'Enabled' if ai_available else 'Disabled'}")
    print()
    
    try:
        main_selenium(max_decisions=max_decisions, use_ai=ai_available)
        print("\n🎉 Scraping completed successfully!")
        print("📄 Check the data/ directory for your CSV output")
        
    except KeyboardInterrupt:
        print("\n❌ Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Scraping failed: {e}")
        sys.exit(1)