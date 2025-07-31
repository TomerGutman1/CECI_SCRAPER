"""Selenium-based scraper for the Israeli Government decisions catalog page."""

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse
from ..utils.selenium import SeleniumWebDriver
from ..config import BASE_CATALOG_URL, CATALOG_PARAMS, BASE_DECISION_URL

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
            
            # Pattern 1: Standard decision page links with all suffix variations
            # Handles: dec3284-2025, dec3173a-2025, dec3172-2025a
            pattern1 = r'/he/pages/dec\d+[a-z]?-\d{4}[a-z]?'
            links1 = driver.find_links_with_pattern(soup, pattern1)
            decision_urls.extend(links1)
            
            # Pattern 2: Any link containing 'dec' and numbers (backup)
            pattern2 = r'/.*dec.*\d+'
            links2 = driver.find_links_with_pattern(soup, pattern2)
            decision_urls.extend(links2)
            
            # Remove duplicates and filter to actual decision pages
            decision_urls = list(set(decision_urls))
            filtered_urls = []
            
            for url in decision_urls:
                # More comprehensive filtering for all suffix variations
                if re.search(r'/he/pages/dec\d+[a-z]?-\d{4}[a-z]?', url):
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
            
            # Sort URLs by decision number (newest first) before limiting
            def extract_decision_number(url):
                """Extract decision number from URL for sorting, handling all suffix variations."""
                # Handle all patterns: dec3284-2025, dec3173a-2025, dec3172-2025a
                match = re.search(r'/dec(\d+)([a-z]?)-(\d{4})([a-z]?)', url)
                if match:
                    decision_num = int(match.group(1))
                    prefix_suffix = match.group(2) or ""  # Empty string if no prefix suffix
                    year = int(match.group(3))
                    postfix_suffix = match.group(4) or ""  # Empty string if no postfix suffix
                    
                    # Create sorting key: (year desc, decision_num desc, prefix_suffix desc, postfix_suffix desc)
                    # Use negative values for descending order
                    suffix_order = ord(prefix_suffix) if prefix_suffix else 0
                    postfix_order = ord(postfix_suffix) if postfix_suffix else 0
                    
                    return (-year, -decision_num, -suffix_order, -postfix_order)
                return (0, 0, 0, 0)  # Default for unparseable URLs
            
            # Sort by decision number (newest first)
            decision_urls.sort(key=extract_decision_number)
            
            logger.info(f"Sorted {len(decision_urls)} URLs by decision number (newest first)")
            
            # Final limiting after sorting
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


def find_correct_url_in_catalog(decision_number: str, max_search_decisions: int = 100) -> Optional[str]:
    """
    Search the catalog for the correct URL for a given decision number.
    This is used when a URL fails and we need to find the actual working URL.
    
    Args:
        decision_number: The decision number to search for (e.g., "3173")
        max_search_decisions: How many decisions to search through
        
    Returns:
        The correct URL if found, None otherwise
    """
    logger.info(f"Searching catalog for correct URL for decision {decision_number}")
    
    try:
        # Get a large batch of URLs from catalog to search through
        catalog_urls = extract_decision_urls_from_catalog_selenium(max_decisions=max_search_decisions)
        
        # Look for URLs that match this decision number
        possible_urls = []
        for url in catalog_urls:
            # Extract decision number from each URL
            match = re.search(r'/dec(\d+)([a-z]?)-(\d{4})([a-z]?)', url)
            if match and match.group(1) == decision_number:
                possible_urls.append(url)
        
        if possible_urls:
            logger.info(f"Found {len(possible_urls)} possible URLs for decision {decision_number}: {possible_urls}")
            # Return the first match (they should all be for the same decision)
            return possible_urls[0]
        else:
            logger.warning(f"No URLs found in catalog for decision {decision_number}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to search catalog for decision {decision_number}: {e}")
        return None


def try_url_variations(base_url: str, decision_number: str) -> Optional[str]:
    """
    Try minimal URL variations when catalog search fails.
    Only tries adding single 'a' suffix to number or year.
    
    Args:
        base_url: The original URL that failed
        decision_number: The decision number
        
    Returns:
        Working URL if found, None otherwise
    """
    logger.info(f"Trying minimal URL variations for decision {decision_number}")
    
    # Extract base components
    match = re.search(r'(/he/pages/dec)(\d+)(-\d{4})', base_url)
    if not match:
        return None
    
    prefix, num, suffix = match.groups()
    
    # Try only these minimal variations:
    variations = [
        f"{prefix}{num}a{suffix}",  # dec3173a-2025
        f"{prefix}{num}{suffix}a"   # dec3173-2025a
    ]
    
    for variation_url in variations:
        try:
            logger.info(f"Testing URL variation: {variation_url}")
            # Quick test if URL returns meaningful content
            with SeleniumWebDriver(headless=True) as driver:
                soup = driver.get_page_with_js(variation_url, wait_time=5)
                content = soup.get_text()
                
                # Check if we got meaningful Hebrew content
                if len(content) > 200 and any(char > '\u0590' for char in content):
                    logger.info(f"Found working URL variation: {variation_url}")
                    return variation_url
                    
        except Exception as e:
            logger.debug(f"URL variation {variation_url} failed: {e}")
            continue
    
    logger.warning(f"No working URL variations found for decision {decision_number}")
    return None


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