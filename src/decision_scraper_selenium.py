"""Selenium-based scraper for individual Israeli Government decision pages."""

import logging
import re
from datetime import datetime
from typing import Dict, Optional
from selenium_utils import SeleniumWebDriver
from config import HEBREW_LABELS, GOVERNMENT_NUMBER, PRIME_MINISTER

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


def extract_and_format_date(text: str) -> str:
    """Extract DD.MM.YYYY date from text and convert to YYYY-MM-DD format."""
    if not text:
        return ""
    
    # Look for DD.MM.YYYY pattern
    date_pattern = r'\b(\d{2})\.(\d{2})\.(\d{4})\b'
    match = re.search(date_pattern, text)
    
    if match:
        day, month, year = match.groups()
        try:
            # Validate and convert to YYYY-MM-DD format
            parsed_date = datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y")
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            logger.warning(f"Invalid date format found: {match.group()}")
            return ""
    
    logger.warning(f"No valid date pattern DD.MM.YYYY found in text: {text[:100]}...")
    return ""


def extract_committee_name(text: str) -> str:
    """Extract only the committee name (2-3 words) after 'ועדות שרים:' before the next section."""
    if not text:
        return ""
    
    # Look for the committee label
    committee_label = 'ועדות שרים:'
    if committee_label not in text:
        return ""
    
    # Find the position after the label
    label_pos = text.find(committee_label)
    after_label = text[label_pos + len(committee_label):].strip()
    
    # Extract until we hit common section separators or get too many words
    # Common separators: "ממשלה:", "תאריך", "נושא", "מחליטים:", "החלטה"
    separators = ['ממשלה:', 'תאריך', 'נושא', 'מחליטים:', 'החלטה', 'פרסום:', 'יחידות:']
    
    # Find the earliest separator
    min_pos = len(after_label)
    for sep in separators:
        pos = after_label.find(sep)
        if pos != -1 and pos < min_pos:
            min_pos = pos
    
    # Get text before the separator
    committee_text = after_label[:min_pos].strip()
    
    # Split into words and take maximum 4 words (to be safe)
    words = committee_text.split()
    if len(words) > 4:
        words = words[:4]
    
    result = ' '.join(words).strip()
    
    # Clean up common artifacts
    result = result.rstrip('.,;:()[]')
    
    return clean_hebrew_text(result)


def find_text_after_label_in_content(content: str, label: str) -> Optional[str]:
    """Find text that appears after a specific Hebrew label in content."""
    if label not in content:
        return None
    
    # Find the position of the label
    label_pos = content.find(label)
    if label_pos == -1:
        return None
    
    # Get text after the label
    after_label = content[label_pos + len(label):].strip()
    
    # Take everything until the next line break or significant delimiter
    lines = after_label.split('\n')
    if lines:
        result = lines[0].strip()
        
        # Remove common punctuation that might be attached
        result = result.rstrip('.,;:')
        
        if result:
            return clean_hebrew_text(result)
    
    return None


def extract_hebrew_field_from_soup(soup, label: str) -> Optional[str]:
    """Extract Hebrew field using multiple strategies."""
    # Strategy 1: Look in the full text content
    full_text = soup.get_text()
    result = find_text_after_label_in_content(full_text, label)
    if result:
        return result
    
    # Strategy 2: Look in specific elements that might contain the data
    for element in soup.find_all(['div', 'p', 'span', 'td']):
        elem_text = element.get_text()
        if label in elem_text:
            result = find_text_after_label_in_content(elem_text, label)
            if result:
                return result
    
    return None


def extract_decision_title_from_soup(soup) -> str:
    """Extract the decision title from the page using multiple strategies."""
    # Strategy 1: Standard title selectors
    title_selectors = [
        'h1',
        '.title',
        '.decision-title', 
        '.page-title',
        '[class*="title"]',
        '[class*="heading"]'
    ]
    
    for selector in title_selectors:
        title_elem = soup.select_one(selector)
        if title_elem:
            title = title_elem.get_text().strip()
            if title and len(title) > 5 and any(char > '\u0590' for char in title):  # Contains Hebrew
                return clean_hebrew_text(title)
    
    # Strategy 2: Look for HTML title
    if soup.title:
        title = soup.title.get_text().strip()
        if title and len(title) > 5:
            return clean_hebrew_text(title)
    
    # Strategy 3: Look for the largest text block that contains Hebrew
    for element in soup.find_all(['h1', 'h2', 'h3', 'div']):
        text = element.get_text().strip()
        if len(text) > 10 and len(text) < 200 and any(char > '\u0590' for char in text):
            return clean_hebrew_text(text)
    
    return ""


def extract_decision_content_from_soup(soup) -> str:
    """Extract the main decision content from the page."""
    # Strategy 1: Look for main content containers
    content_selectors = [
        '[class*="content"]',
        '[class*="decision"]',
        '[class*="body"]',
        '[class*="text"]',
        'main',
        'article',
        '.main-content',
        '#content',
        '[role="main"]'
    ]
    
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            text = content_elem.get_text()
            if len(text) > 200 and any(char > '\u0590' for char in text):  # Contains Hebrew and substantial content
                return clean_hebrew_text(text)
    
    # Strategy 2: Look for the largest text block with Hebrew content
    all_elements = soup.find_all(['div', 'p', 'section', 'article'])
    best_content = ""
    max_length = 0
    
    for element in all_elements:
        text = element.get_text().strip()
        if len(text) > max_length and len(text) > 100 and any(char > '\u0590' for char in text):
            max_length = len(text)
            best_content = text
    
    if best_content:
        return clean_hebrew_text(best_content)
    
    # Strategy 3: Fallback - get all text and filter
    all_text = soup.get_text()
    if len(all_text) > 100:
        return clean_hebrew_text(all_text)
    
    return ""


def scrape_decision_page_selenium(url: str) -> Dict[str, str]:
    """
    Use Selenium to scrape a single decision page and extract all relevant data.
    
    Args:
        url: URL of the decision page
        
    Returns:
        Dictionary containing extracted decision data
    """
    logger.info(f"Scraping decision page with Selenium: {url}")
    
    try:
        with SeleniumWebDriver(headless=True) as driver:
            # Load the page and wait for Hebrew content to appear
            soup = driver.get_page_with_js(
                url,
                wait_for_element=None,  # Don't wait for specific element
                wait_time=10  # Wait for JavaScript to load content
            )
            
            # Additional wait for Hebrew content specifically
            driver.wait_for_content_with_text('החלטה', max_wait=10)
            
            # Get fresh soup after waiting for content
            soup = driver.get_page_with_js(url, wait_time=2)
            
            logger.info(f"Successfully loaded decision page (HTML length: {len(str(soup))})")
            
            # Extract decision number from URL
            decision_number = extract_decision_number_from_url(url)
            
            # Extract data using Hebrew labels
            decision_date_raw = extract_hebrew_field_from_soup(soup, HEBREW_LABELS['date'])
            decision_date = extract_and_format_date(decision_date_raw) if decision_date_raw else ""
            
            # If we couldn't extract decision number from URL, try to find it in content
            if not decision_number:
                decision_number = extract_hebrew_field_from_soup(soup, HEBREW_LABELS['number'])
            
            # Extract title and content
            decision_title = extract_decision_title_from_soup(soup)
            decision_content = extract_decision_content_from_soup(soup)
            
            # Extract committee directly from content (most reliable method)
            committee = extract_committee_name(decision_content)
            
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
            logger.info(f"  - Has Hebrew content: {any(char > '\\u0590' for char in decision_content)}")
            
            return result
            
    except Exception as e:
        logger.error(f"Failed to scrape decision page {url} with Selenium: {e}")
        raise


def test_decision_scraping():
    """Test the Selenium-based decision scraping with a real URL."""
    test_url = "https://www.gov.il/he/pages/dec3283-2025"  # Recent decision found by catalog scraper
    
    try:
        logger.info(f"Testing Selenium-based decision scraping with: {test_url}")
        data = scrape_decision_page_selenium(test_url)
        
        print(f"✅ Successfully scraped decision:")
        for key, value in data.items():
            if len(str(value)) > 100:
                print(f"   {key}: {str(value)[:100]}...")
            else:
                print(f"   {key}: {value}")
        
        # Check if we got meaningful content
        has_content = len(data.get('decision_content', '')) > 100
        has_hebrew = any(char > '\u0590' for char in data.get('decision_content', ''))
        
        if has_content and has_hebrew:
            print("✅ Content extraction successful!")
            return True
        else:
            print("⚠️  Content extraction needs improvement")
            return False
            
    except Exception as e:
        print(f"❌ Decision scraping failed: {e}")
        return False


if __name__ == "__main__":
    # Test the decision scraper
    test_decision_scraping()