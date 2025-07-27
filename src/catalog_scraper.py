"""Scraper for the Israeli Government decisions catalog page."""

import requests
import time
import logging
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import urljoin, urlparse
import re

from config import BASE_CATALOG_URL, CATALOG_PARAMS, BASE_DECISION_URL, HEADERS, MAX_RETRIES, RETRY_DELAY

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def make_request_with_retry(url: str, params: dict = None) -> requests.Response:
    """Make HTTP request with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Attempting to fetch {url} (attempt {attempt + 1}/{MAX_RETRIES})")
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise
    

def extract_decision_urls_from_catalog(max_decisions: int = 5) -> List[str]:
    """
    Fetch the catalog page and extract decision URLs.
    
    Args:
        max_decisions: Maximum number of decision URLs to extract
        
    Returns:
        List of decision URLs
    """
    logger.info(f"Fetching catalog page to extract {max_decisions} decision URLs")
    
    # Update params for this request
    params = CATALOG_PARAMS.copy()
    params['limit'] = max_decisions
    
    try:
        response = make_request_with_retry(BASE_CATALOG_URL, params)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        logger.info(f"Successfully fetched catalog page (status: {response.status_code})")
        
        # Look for decision links - these typically follow pattern /he/pages/dec{number}-{year}
        decision_urls = []
        
        # Search for all links containing decision pattern
        all_links = soup.find_all('a', href=True)
        logger.info(f"Found {len(all_links)} total links on catalog page")
        
        for link in all_links:
            href = link.get('href', '')
            
            # Look for decision page pattern: /he/pages/dec{number}-{year}
            if re.match(r'/he/pages/dec\d+-\d{4}', href):
                full_url = urljoin(BASE_DECISION_URL, href)
                decision_urls.append(full_url)
                logger.info(f"Found decision URL: {full_url}")
                
                if len(decision_urls) >= max_decisions:
                    break
        
        # If we didn't find enough with the strict pattern, try a broader search
        if len(decision_urls) < max_decisions:
            logger.warning(f"Only found {len(decision_urls)} URLs with strict pattern, trying broader search")
            
            # Look for any links containing 'dec' and a number
            for link in all_links:
                href = link.get('href', '')
                if '/pages/' in href and 'dec' in href and any(char.isdigit() for char in href):
                    full_url = urljoin(BASE_DECISION_URL, href)
                    if full_url not in decision_urls:
                        decision_urls.append(full_url)
                        logger.info(f"Found additional decision URL: {full_url}")
                        
                        if len(decision_urls) >= max_decisions:
                            break
        
        if not decision_urls:
            logger.error("No decision URLs found! The page structure might have changed.")
            # Log a sample of the page content for debugging
            logger.debug(f"Page content sample: {soup.get_text()[:500]}...")
            
        logger.info(f"Extracted {len(decision_urls)} decision URLs from catalog")
        return decision_urls[:max_decisions]
        
    except Exception as e:
        logger.error(f"Failed to extract decision URLs from catalog: {e}")
        raise


if __name__ == "__main__":
    # Test the catalog scraper
    try:
        urls = extract_decision_urls_from_catalog(5)
        print(f"Found {len(urls)} decision URLs:")
        for i, url in enumerate(urls, 1):
            print(f"{i}. {url}")
    except Exception as e:
        print(f"Error: {e}")