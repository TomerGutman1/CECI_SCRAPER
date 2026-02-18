"""Selenium-based scraper for individual Israeli Government decision pages."""

import logging
import re
from datetime import datetime
from typing import Dict, Optional
from ..utils.selenium import SeleniumWebDriver
from ..config import HEBREW_LABELS, GOVERNMENT_NUMBER, PRIME_MINISTER

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_decision_number_from_url(url: str) -> Optional[str]:
    """Extract decision number from URL like /he/pages/dec2980-2025 or /he/pages/dec-3820-2026."""
    match = re.search(r'/dec-?(\d+)-\d{4}', url)
    return match.group(1) if match else None


def build_deterministic_decision_url(
    government_number: str,
    decision_number: str,
    decision_date: str = None,
    try_variations: bool = False
) -> List[str]:
    """
    Build deterministic decision URLs based on known patterns.

    CRITICAL: Do not trust catalog API URLs - they have systematic errors.
    Government 28 decisions have +20M offset issues in catalog URLs.

    Args:
        government_number: Government number (e.g., "37", "28")
        decision_number: Decision number (e.g., "3173", "275")
        decision_date: Decision date in YYYY-MM-DD format (optional, for year extraction)
        try_variations: If True, return multiple URL variations to try

    Returns:
        List of URLs to try in order of preference

    URL Patterns Observed:
    - Standard: https://www.gov.il/he/pages/{gov_num}_des{decision_num}
    - Alternative: https://www.gov.il/he/pages/dec{decision_num}-{year}
    - Variations: a, b, c suffixes for multiple decisions same number
    """
    if not government_number or not decision_number:
        logger.warning(f"Invalid parameters: gov={government_number}, decision={decision_number}")
        return []

    # Clean inputs
    gov_num = str(government_number).strip()
    dec_num = str(decision_number).strip()

    # Extract year from date if available
    year = None
    if decision_date and decision_date.count('-') >= 2:
        try:
            year = decision_date.split('-')[0]
        except (ValueError, IndexError):
            year = None

    urls = []

    # Pattern 1: Primary deterministic format based on government
    # This is the most reliable pattern we've observed
    primary_url = f"https://www.gov.il/he/pages/{gov_num}_des{dec_num}"
    urls.append(primary_url)

    # Pattern 2: Alternative dec format (with year if available)
    if year:
        alt_url_with_year = f"https://www.gov.il/he/pages/dec{dec_num}-{year}"
        urls.append(alt_url_with_year)

    # Pattern 3: Alternative without year (fallback)
    alt_url = f"https://www.gov.il/he/pages/dec{dec_num}"
    urls.append(alt_url)

    # Pattern 4: Government-specific corrections for known issues
    if gov_num == "28":
        # Gov 28 has systematic +20M offset issues in some URLs
        # Try the offset correction
        try:
            offset_dec = int(dec_num) + 20000000
            offset_url = f"https://www.gov.il/he/pages/{gov_num}_des{offset_dec}"
            urls.append(offset_url)

            if year:
                offset_year_url = f"https://www.gov.il/he/pages/dec{offset_dec}-{year}"
                urls.append(offset_year_url)
        except ValueError:
            pass

    if try_variations:
        # Pattern 5: Suffix variations (a, b, c) for duplicate decision numbers
        base_patterns = [
            f"https://www.gov.il/he/pages/{gov_num}_des{dec_num}",
            f"https://www.gov.il/he/pages/dec{dec_num}",
        ]

        if year:
            base_patterns.append(f"https://www.gov.il/he/pages/dec{dec_num}-{year}")

        for pattern in base_patterns:
            for suffix in ['a', 'b', 'c']:
                # Add suffix before file extension or at end
                variation_url = pattern + suffix
                urls.append(variation_url)

                # Also try with year suffix
                if year and 'dec' in pattern and '-' not in pattern:
                    year_suffix_url = f"{pattern}{suffix}-{year}"
                    urls.append(year_suffix_url)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    logger.info(f"Generated {len(unique_urls)} URL candidates for {gov_num}_{dec_num}")
    return unique_urls


def validate_url_against_decision_key(url: str, decision_key: str) -> Dict[str, any]:
    """
    Validate that a URL matches the expected decision key.

    Args:
        url: The URL to validate
        decision_key: Expected decision key format: {gov_num}_{decision_num}

    Returns:
        Dict with validation results:
        {
            'valid': bool,
            'url_decision_number': str,
            'expected_decision_number': str,
            'difference': int,
            'url_pattern': str,
            'issues': List[str]
        }
    """
    result = {
        'valid': False,
        'url_decision_number': None,
        'expected_decision_number': None,
        'difference': 0,
        'url_pattern': 'unknown',
        'issues': []
    }

    # Parse decision key
    if not decision_key or '_' not in decision_key:
        result['issues'].append(f"Invalid decision_key format: {decision_key}")
        return result

    try:
        gov_num, expected_dec_num = decision_key.split('_', 1)
        result['expected_decision_number'] = expected_dec_num
    except ValueError:
        result['issues'].append(f"Cannot parse decision_key: {decision_key}")
        return result

    # Extract decision number from URL
    url_dec_num = extract_decision_number_from_url(url)
    if not url_dec_num:
        # Try alternative patterns
        patterns = [
            r'_des(\d+)',  # gov_num_des123
            r'/(\d+)_des',  # /123_des
            r'dec(\d+)',   # dec123
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                url_dec_num = match.group(1)
                break

    if not url_dec_num:
        result['issues'].append(f"Cannot extract decision number from URL: {url}")
        return result

    result['url_decision_number'] = url_dec_num

    # Identify URL pattern
    if '_des' in url:
        result['url_pattern'] = 'gov_des'
    elif '/dec' in url and '-' in url:
        result['url_pattern'] = 'dec_year'
    elif '/dec' in url:
        result['url_pattern'] = 'dec_simple'
    else:
        result['url_pattern'] = 'unknown'

    # Compare numbers
    # Check if decision numbers match (handle letters like 2433א)
    if expected_dec_num == url_dec_num:
        # Exact match (including letters)
        result['valid'] = True
        result['difference'] = 0
    else:
        # Try numeric comparison if both are purely numeric
        try:
            expected_num = int(expected_dec_num)
            url_num = int(url_dec_num)
            result['difference'] = url_num - expected_num

            # Validation logic for numeric differences
            if result['difference'] == 0:
                result['valid'] = True
            else:
                result['issues'].append(
                    f"Number mismatch: URL has {url_num}, expected {expected_num} "
                    f"(difference: {result['difference']:+d})"
                )

                # Check for known systematic errors
                if abs(result['difference']) > 1000000:
                    result['issues'].append("Systematic offset detected (>1M difference)")

        except ValueError:
            # At least one contains letters - check for exact match
            if expected_dec_num != url_dec_num:
                result['issues'].append(
                    f"Decision number mismatch: URL has '{url_dec_num}', expected '{expected_dec_num}'"
                )

    return result


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


def extract_and_format_date(text: str) -> Optional[str]:
    """
    Extract DD.MM.YYYY date from text and convert to YYYY-MM-DD format.

    Args:
        text: Text containing a date

    Returns:
        Formatted date string (YYYY-MM-DD) or None if extraction fails
    """
    if not text:
        return None

    # Look for DD.MM.YYYY pattern
    date_pattern = r'\b(\d{2})\.(\d{2})\.(\d{4})\b'
    match = re.search(date_pattern, text)

    if match:
        day, month, year = match.groups()
        try:
            # Validate and convert to YYYY-MM-DD format
            parsed_date = datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y")

            # Validate reasonable date range (1948 - today + 1 year buffer)
            min_date = datetime(1948, 1, 1)
            max_date = datetime.now().replace(year=datetime.now().year + 1)

            if parsed_date < min_date or parsed_date > max_date:
                logger.warning(f"Date {match.group()} is outside valid range (1948-{max_date.year})")
                return None

            return parsed_date.strftime("%Y-%m-%d")

        except ValueError:
            logger.warning(f"Invalid date format found: {match.group()}")
            return None

    logger.warning(f"No valid date pattern DD.MM.YYYY found in text: {text[:100]}...")
    return None


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
            # Load the page with sufficient wait for SPA to render
            soup = driver.get_page_with_js(
                url,
                wait_for_element=None,
                wait_time=15
            )

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


def scrape_decision_content_only(url: str, wait_time: int = 15, swd=None) -> str:
    """
    Scrape only the decision content body from a decision page.
    Metadata (title, date, number, committee) comes from the catalog API.

    Args:
        url: Full URL of the decision page
        wait_time: Seconds to wait for JavaScript rendering (default 15)
        swd: Optional SeleniumWebDriver instance to reuse (avoids creating new Chrome)

    Returns:
        The decision content text, or empty string on failure
    """
    logger.info(f"Scraping decision content from: {url} (wait_time={wait_time}s)")
    try:
        if swd:
            soup = swd.navigate_to(url, wait_time=wait_time)
            content = extract_decision_content_from_soup(soup)
            logger.info(f"Extracted content: {len(content)} chars")
            return content
        else:
            with SeleniumWebDriver(headless=True) as driver:
                soup = driver.get_page_with_js(url, wait_time=wait_time)
                content = extract_decision_content_from_soup(soup)
                logger.info(f"Extracted content: {len(content)} chars")
                return content
    except Exception as e:
        logger.error(f"Failed to scrape content from {url}: {e}")
        return ""


def _build_result_from_meta(decision_meta: dict, content: str) -> Dict[str, str]:
    """Build a full result dict by merging API metadata with scraped content."""
    return {
        'decision_url': decision_meta['url'],
        'decision_number': decision_meta.get('decision_number', ''),
        'decision_date': decision_meta.get('decision_date', ''),
        'committee': decision_meta.get('committee', ''),
        'decision_title': decision_meta.get('title', ''),
        'decision_content': content,
        'government_number': str(GOVERNMENT_NUMBER),
        'prime_minister': PRIME_MINISTER,
        'decision_key': f"{GOVERNMENT_NUMBER}_{decision_meta.get('decision_number', '')}"
    }


def scrape_decision_with_url_recovery(decision_meta: dict, wait_time: int = 15, swd=None) -> Optional[Dict[str, str]]:
    """
    Scrape a decision's content with deterministic URL construction and recovery.
    CRITICAL: Uses deterministic URL building instead of trusting catalog URLs.

    Args:
        decision_meta: Dict with keys: url, title, decision_number, decision_date, committee
        wait_time: Seconds to wait for JavaScript rendering (default 15)
        swd: Optional SeleniumWebDriver instance to reuse (avoids creating new Chrome)

    Returns:
        Dictionary containing decision data, or None if all attempts fail
    """
    original_url = decision_meta['url']
    decision_number = decision_meta.get('decision_number', '') or extract_decision_number_from_url(original_url)
    government_number = decision_meta.get('government_number')
    decision_date = decision_meta.get('decision_date')

    logger.info(f"Scraping decision {decision_number} with deterministic URL recovery")

    if not decision_number:
        logger.error(f"Cannot determine decision number for: {original_url}")
        return None

    # Build decision key for validation
    decision_key = f"{government_number}_{decision_number}" if government_number else None

    # Validate original URL if we have the decision key
    url_validation = None
    if decision_key:
        url_validation = validate_url_against_decision_key(original_url, decision_key)
        if not url_validation['valid']:
            logger.warning(
                f"Original URL validation failed for {decision_key}: "
                f"{url_validation['issues']}"
            )

    # First attempt: Try the original URL (even if validation failed)
    content = scrape_decision_content_only(original_url, wait_time=wait_time, swd=swd)
    if content and len(content) > 50:
        logger.info(f"Original URL worked for decision {decision_number}")
        if url_validation and not url_validation['valid']:
            logger.warning(f"URL validation failed but content retrieved for {decision_key}")
        return _build_result_from_meta(decision_meta, content)

    logger.warning(f"Original URL returned empty content for decision {decision_number}")

    # Second attempt: Use deterministic URL construction
    if government_number:
        logger.info(f"Building deterministic URLs for {government_number}_{decision_number}")
        candidate_urls = build_deterministic_decision_url(
            government_number=government_number,
            decision_number=decision_number,
            decision_date=decision_date,
            try_variations=False  # Start with primary patterns only
        )

        for i, candidate_url in enumerate(candidate_urls):
            if candidate_url == original_url:
                # Skip original URL since we already tried it
                continue

            logger.info(f"Trying deterministic URL {i+1}/{len(candidate_urls)}: {candidate_url}")

            # Validate the candidate URL
            validation = validate_url_against_decision_key(candidate_url, decision_key)
            if validation['valid']:
                logger.info(f"URL validation passed for {candidate_url}")
            else:
                logger.info(f"URL validation issues: {validation['issues']}")

            content = scrape_decision_content_only(candidate_url, wait_time=wait_time, swd=swd)
            if content and len(content) > 50:
                logger.info(f"Deterministic URL worked: {candidate_url}")
                meta_with_url = {**decision_meta, 'url': candidate_url}
                return _build_result_from_meta(meta_with_url, content)

    # Third attempt: Try variations if basic patterns failed
    if government_number:
        logger.info(f"Trying URL variations for {government_number}_{decision_number}")
        variation_urls = build_deterministic_decision_url(
            government_number=government_number,
            decision_number=decision_number,
            decision_date=decision_date,
            try_variations=True
        )

        # Filter out URLs we already tried
        already_tried = {original_url}
        if government_number:
            candidate_urls = build_deterministic_decision_url(
                government_number, decision_number, decision_date, False
            )
            already_tried.update(candidate_urls)

        for i, variation_url in enumerate(variation_urls):
            if variation_url in already_tried:
                continue

            logger.info(f"Trying variation URL {i+1}: {variation_url}")
            content = scrape_decision_content_only(variation_url, wait_time=wait_time, swd=swd)
            if content and len(content) > 50:
                logger.info(f"Variation URL worked: {variation_url}")
                meta_with_url = {**decision_meta, 'url': variation_url}
                return _build_result_from_meta(meta_with_url, content)

    # Fourth attempt: Legacy fallback to catalog search (as last resort)
    try:
        from .catalog import find_correct_url_in_catalog
        logger.info(f"Fallback: searching catalog for correct URL for decision {decision_number}")
        correct_url = find_correct_url_in_catalog(decision_number, swd=swd)

        if correct_url and correct_url != original_url:
            logger.info(f"Found different URL in catalog: {correct_url}")

            # Validate catalog URL before using it
            if decision_key:
                catalog_validation = validate_url_against_decision_key(correct_url, decision_key)
                if not catalog_validation['valid']:
                    logger.warning(
                        f"Catalog URL validation failed: {catalog_validation['issues']} "
                        f"- using anyway as last resort"
                    )

            content = scrape_decision_content_only(correct_url, wait_time=wait_time, swd=swd)
            if content and len(content) > 50:
                logger.info(f"Catalog URL worked for decision {decision_number}")
                meta_with_url = {**decision_meta, 'url': correct_url}
                return _build_result_from_meta(meta_with_url, content)
    except Exception as e:
        logger.warning(f"Catalog search failed for decision {decision_number}: {e}")

    logger.error(f"All URL recovery attempts failed for decision {decision_number}")
    return None


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