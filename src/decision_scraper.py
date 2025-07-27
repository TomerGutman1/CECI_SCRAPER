"""Scraper for individual Israeli Government decision pages."""

import requests
import logging
import re
from bs4 import BeautifulSoup
from typing import Dict, Optional
from urllib.parse import urlparse

from config import HEADERS, MAX_RETRIES, RETRY_DELAY, HEBREW_LABELS, GOVERNMENT_NUMBER, PRIME_MINISTER
from catalog_scraper import make_request_with_retry

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_decision_number_from_url(url: str) -> Optional[str]:
    """Extract decision number from URL like /he/pages/dec2980-2025."""
    match = re.search(r'/dec(\d+)-\d{4}', url)
    return match.group(1) if match else None


def clean_hebrew_text(text: str) -> str:
    """Clean and normalize Hebrew text."""
    if not text:
        return ""
    
    # Remove extra whitespace and normalize
    text = ' '.join(text.split())
    
    # Remove common HTML artifacts
    text = text.replace('\u200b', '')  # Zero-width space
    text = text.replace('\u200e', '')  # Left-to-right mark
    text = text.replace('\u200f', '')  # Right-to-left mark
    
    return text.strip()


def find_text_after_label(soup: BeautifulSoup, label: str) -> Optional[str]:
    """Find text that appears after a specific Hebrew label."""
    # Look for the label in various elements
    for element in soup.find_all(text=True):
        if label in element:
            # Found the label, now try to get the text that follows
            parent = element.parent
            if parent:
                # Get all text from this element and siblings
                full_text = parent.get_text()
                
                # Find the position of the label and extract what comes after
                label_pos = full_text.find(label)
                if label_pos != -1:
                    after_label = full_text[label_pos + len(label):].strip()
                    
                    # Take everything until the next line break or significant whitespace
                    lines = after_label.split('\n')
                    if lines:
                        result = lines[0].strip()
                        
                        # Remove common punctuation that might be attached
                        result = result.rstrip('.,;:')
                        
                        if result:
                            return clean_hebrew_text(result)
    
    return None


def extract_decision_content(soup: BeautifulSoup) -> str:
    """Extract the main decision content from the page."""
    # Look for main content areas (this may need adjustment based on actual HTML structure)
    content_selectors = [
        '.decision-content',
        '.main-content', 
        '[role="main"]',
        '.content',
        'main',
        'article'
    ]
    
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            text = content_elem.get_text()
            if len(text) > 100:  # Ensure we got substantial content
                return clean_hebrew_text(text)
    
    # Fallback: get all paragraph text
    paragraphs = soup.find_all('p')
    if paragraphs:
        content = ' '.join([p.get_text() for p in paragraphs])
        if len(content) > 100:
            return clean_hebrew_text(content)
    
    # Last resort: get all text but try to filter out navigation/header content
    all_text = soup.get_text()
    return clean_hebrew_text(all_text)


def extract_decision_title(soup: BeautifulSoup) -> str:
    """Extract the decision title from the page."""
    # Try different title selectors
    title_selectors = [
        'h1',
        '.title',
        '.decision-title',
        '.page-title',
        'title'
    ]
    
    for selector in title_selectors:
        title_elem = soup.select_one(selector)
        if title_elem:
            title = title_elem.get_text().strip()
            if title and len(title) > 5:  # Ensure it's not just whitespace or very short
                return clean_hebrew_text(title)
    
    return ""


def scrape_decision_page(url: str) -> Dict[str, str]:
    """
    Scrape a single decision page and extract all relevant data.
    
    Args:
        url: URL of the decision page
        
    Returns:
        Dictionary containing extracted decision data
    """
    logger.info(f"Scraping decision page: {url}")
    
    try:
        response = make_request_with_retry(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        logger.info(f"Successfully fetched decision page (status: {response.status_code})")
        
        # Extract decision number from URL
        decision_number = extract_decision_number_from_url(url)
        
        # Extract data using Hebrew labels
        decision_date = find_text_after_label(soup, HEBREW_LABELS['date'])
        committee = find_text_after_label(soup, HEBREW_LABELS['committee'])
        
        # If we couldn't extract decision number from URL, try to find it in content
        if not decision_number:
            decision_number = find_text_after_label(soup, HEBREW_LABELS['number'])
        
        # Extract title and content
        decision_title = extract_decision_title(soup)
        decision_content = extract_decision_content(soup)
        
        # Generate decision key
        decision_key = f"{GOVERNMENT_NUMBER}_{decision_number}" if decision_number else ""
        
        # Prepare the result
        result = {
            'decision_url': url,
            'decision_number': decision_number or "",
            'decision_date': decision_date or "",
            'committee': committee or "",
            'decision_title': decision_title,
            'decision_content': decision_content,
            'government_number': str(GOVERNMENT_NUMBER),
            'prime_minister': PRIME_MINISTER,
            'decision_key': decision_key
        }
        
        # Log what we extracted
        logger.info(f"Extracted data for decision {decision_number}:")
        logger.info(f"  - Date: {decision_date}")
        logger.info(f"  - Committee: {committee}")
        logger.info(f"  - Title length: {len(decision_title)} chars")
        logger.info(f"  - Content length: {len(decision_content)} chars")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to scrape decision page {url}: {e}")
        raise


if __name__ == "__main__":
    # Test with a sample decision URL
    test_url = "https://www.gov.il/he/pages/dec2980-2025"
    
    try:
        data = scrape_decision_page(test_url)
        print("Extracted decision data:")
        for key, value in data.items():
            if len(str(value)) > 100:
                print(f"{key}: {str(value)[:100]}...")
            else:
                print(f"{key}: {value}")
    except Exception as e:
        print(f"Error: {e}")