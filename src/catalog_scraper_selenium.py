"""Selenium-based scraper for the Israeli Government decisions catalog page."""

import logging
import re
from urllib.parse import urljoin, urlparse
from selenium_utils import SeleniumWebDriver
from config import BASE_CATALOG_URL, CATALOG_PARAMS, BASE_DECISION_URL

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_decision_urls_from_catalog_selenium(max_decisions: int = 5) -> list:
    """
    Use Selenium to fetch the catalog page and extract decision URLs.
    
    Args:
        max_decisions: Maximum number of decision URLs to extract
        
    Returns:
        List of decision URLs
    """
    logger.info(f"Using Selenium to extract {max_decisions} decision URLs from catalog")
    
    # Build the full URL with parameters
    params = CATALOG_PARAMS.copy()
    params['limit'] = max_decisions
    
    # Convert params to query string
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    full_url = f"{BASE_CATALOG_URL}?{query_string}"
    
    try:
        with SeleniumWebDriver(headless=True) as driver:
            # Load the page and wait for content
            logger.info(f"Loading catalog page: {full_url}")
            soup = driver.get_page_with_js(
                full_url, 
                wait_for_element=None,  # We'll wait generally and then check
                wait_time=15  # Wait longer for the SPA to load
            )
            
            logger.info(f"Page loaded, searching for decision links...")
            
            # Look for decision links with various patterns
            decision_urls = []
            
            # Pattern 1: Standard decision page links
            pattern1 = r'/he/pages/dec\d+-\d{4}'
            links1 = driver.find_links_with_pattern(soup, pattern1)
            decision_urls.extend(links1)
            
            # Pattern 2: Any link containing 'dec' and numbers
            pattern2 = r'/.*dec.*\d+'
            links2 = driver.find_links_with_pattern(soup, pattern2)
            decision_urls.extend(links2)
            
            # Remove duplicates and filter to actual decision pages
            decision_urls = list(set(decision_urls))
            filtered_urls = []
            
            for url in decision_urls:
                # More strict filtering
                if re.search(r'/he/pages/dec\d+-\d{4}', url):
                    filtered_urls.append(url)
            
            decision_urls = filtered_urls
            
            # If we still don't have enough, try a different approach
            if len(decision_urls) < max_decisions:
                logger.warning(f"Only found {len(decision_urls)} URLs with strict pattern")
                
                # Look for any element that might contain decision information
                # This is more exploratory - we'll search for Hebrew text patterns
                page_text = soup.get_text()
                
                # Look for decision numbers in the text
                decision_numbers = re.findall(r'החלטה.*?(\d{4})', page_text)
                decision_numbers.extend(re.findall(r'מספר.*?(\d{4})', page_text))
                
                # Generate URLs from found decision numbers
                for num in set(decision_numbers):
                    if len(num) == 4:  # Decision numbers are typically 4 digits
                        potential_url = f"https://www.gov.il/he/pages/dec{num}-2025"
                        if potential_url not in decision_urls:
                            decision_urls.append(potential_url)
            
            # Final filtering and limiting
            decision_urls = decision_urls[:max_decisions]
            
            if not decision_urls:
                logger.warning("No decision URLs found even with Selenium!")
                logger.info("This might indicate:")
                logger.info("1. The page structure has changed significantly")
                logger.info("2. The content requires additional waiting time")
                logger.info("3. The site has anti-bot protection")
                
                # Save page source for debugging
                with open('/tmp/catalog_debug.html', 'w', encoding='utf-8') as f:
                    f.write(str(soup))
                logger.info("Saved page source to /tmp/catalog_debug.html for inspection")
            
            logger.info(f"Extracted {len(decision_urls)} decision URLs")
            for i, url in enumerate(decision_urls, 1):
                logger.info(f"  {i}. {url}")
            
            return decision_urls
            
    except Exception as e:
        logger.error(f"Failed to extract decision URLs with Selenium: {e}")
        raise


def test_catalog_scraping():
    """Test the Selenium-based catalog scraping."""
    try:
        logger.info("Testing Selenium-based catalog scraping...")
        urls = extract_decision_urls_from_catalog_selenium(3)
        
        if urls:
            print(f"✅ Found {len(urls)} decision URLs:")
            for i, url in enumerate(urls, 1):
                print(f"   {i}. {url}")
            return True
        else:
            print("❌ No decision URLs found")
            return False
            
    except Exception as e:
        print(f"❌ Catalog scraping failed: {e}")
        return False


if __name__ == "__main__":
    # Test the catalog scraper
    test_catalog_scraping()