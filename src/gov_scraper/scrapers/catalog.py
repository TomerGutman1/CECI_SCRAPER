"""Scraper for the Israeli Government decisions catalog page (API + Selenium)."""

import json
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from ..utils.selenium import SeleniumWebDriver, CloudflareBlockedError
from ..config import BASE_CATALOG_URL, CATALOG_PARAMS, BASE_DECISION_URL, PM_BY_GOVERNMENT

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# gov.il REST API endpoint for decision results
CATALOG_API_URL = (
    "https://www.gov.il/CollectorsWebApi/api/DataCollector/GetResults"
    "?CollectorType=policy&CollectorType=pmopolicy"
    "&Type=30280ed5-306f-4f0b-a11d-cacf05d36648"
    "&culture=he"
)


def _format_date(raw_date: str) -> str:
    """Convert DD.MM.YYYY to YYYY-MM-DD format."""
    if not raw_date:
        return ""
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', raw_date)
    if match:
        try:
            parsed = datetime.strptime(match.group(), "%d.%m.%Y")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def parse_government_field(gov_text: str) -> tuple[str, Optional[str]]:
    """
    Parse Hebrew government text to extract government number and PM name.

    Takes Hebrew government text like "הממשלה ה- 37" or "הממשלה ה- 25, יצחק רבין"
    and returns tuple (gov_num: str, pm_name: str|None)

    Args:
        gov_text: Hebrew government text from API

    Returns:
        Tuple of (government_number: str, prime_minister: str|None)
        Both values can be None if parsing fails
    """
    if not gov_text:
        return (None, None)

    # Extract government number using regex
    gov_match = re.search(r'\d+', gov_text)
    gov_num = gov_match.group() if gov_match else None

    # Extract PM name if present after comma
    pm_name = None
    if ',' in gov_text:
        parts = gov_text.split(',', 1)
        if len(parts) > 1:
            pm_name = parts[1].strip()

    return (gov_num, pm_name)


def extract_entry_from_api_result(result_item: Dict) -> Optional[Dict]:
    """
    Extract a decision entry from a single API result JSON item with complete metadata.

    Takes a single API result JSON item and extracts all metadata: url, title,
    decision_number, decision_date, government_number, prime_minister, committee, description.
    Converts dates from DD.MM.YYYY to YYYY-MM-DD format and uses PM_BY_GOVERNMENT
    lookup if PM not in API.

    Args:
        result_item: Single result dict from API response

    Returns:
        Complete decision metadata dict or None if invalid
    """
    url_path = result_item.get("url", "")
    if not url_path:
        return None

    # Extract metadata from structured tags
    tags = result_item.get("tags", {})
    promoted = tags.get("promotedMetaData", {})
    meta = tags.get("metaData", {})

    # Decision number
    num_list = promoted.get("מספר החלטה", [])
    decision_number = num_list[0].get("title", "") if num_list else ""

    # Publication date (DD.MM.YYYY → YYYY-MM-DD)
    date_list = meta.get("תאריך פרסום", [])
    raw_date = date_list[0].get("title", "") if date_list else ""
    decision_date = _format_date(raw_date)

    # Committee (optional)
    committee_list = meta.get("ועדות שרים", [])
    committee = committee_list[0].get("title", "") if committee_list else ""

    # Government field parsing
    government_number = None
    prime_minister = None

    # Try to extract from government field in metadata
    gov_list = meta.get("ממשלה", [])
    if gov_list and len(gov_list) > 0:
        gov_text = gov_list[0].get("title", "")
        if gov_text:
            government_number, prime_minister = parse_government_field(gov_text)

    # Fallback to PM_BY_GOVERNMENT lookup if PM not found in API
    if government_number and not prime_minister:
        try:
            gov_num_int = int(government_number)
            prime_minister = PM_BY_GOVERNMENT.get(gov_num_int)
        except (ValueError, TypeError):
            pass

    # Build full URL and extract other fields
    full_url = f"{BASE_DECISION_URL}{url_path}"
    title = result_item.get("title", "")
    description = result_item.get("description", "")

    return {
        "url": full_url,
        "title": title,
        "decision_number": decision_number,
        "decision_date": decision_date,
        "government_number": government_number,
        "prime_minister": prime_minister,
        "committee": committee,
        "description": description,
        "url_path": url_path,  # Keep original for pattern analysis
        "raw_api_result": result_item  # Keep full result for debugging
    }


def extract_catalog_via_api(max_decisions: int = 100, session=None) -> List[Dict]:
    """
    Extract decision entries from the gov.il catalog API using curl_cffi (no browser).

    Calls the same catalog REST API as the Selenium version but uses curl_cffi
    with Chrome impersonation instead of a real browser. This is faster and
    avoids all Cloudflare/Chrome issues.

    Args:
        max_decisions: Maximum number of decision entries to extract
        session: Optional curl_cffi Session to reuse

    Returns:
        List of dicts with keys: url, title, decision_number, decision_date, committee, etc.
        Same format as extract_decision_urls_from_catalog_selenium().
    """
    from curl_cffi import requests as curl_requests

    logger.info(f"Fetching {max_decisions} catalog entries via API (no browser)...")

    api_url = f"{CATALOG_API_URL}&skip=0&limit={max_decisions}"

    if session is None:
        session = curl_requests.Session(impersonate="chrome")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = session.get(api_url, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            total = data.get("total", 0)
            results = data.get("results", [])

            logger.info(f"API returned {len(results)} results (total available: {total})")

            decision_entries = []
            for result in results:
                entry = extract_entry_from_api_result(result)
                if entry:
                    decision_entries.append(entry)

            # Sort by decision number (newest first)
            decision_entries.sort(key=lambda d: _extract_decision_sort_key(d["url"]))

            logger.info(f"Extracted {len(decision_entries)} decision entries via API")
            for i, entry in enumerate(decision_entries[:10], 1):
                logger.info(f"  {i}. #{entry['decision_number']} | {entry['decision_date']} | {entry['title'][:60]}")

            if not decision_entries:
                logger.warning("No decision entries found from catalog API!")

            return decision_entries

        except Exception as e:
            if attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                logger.warning(f"Catalog API attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Catalog API failed after {max_retries} attempts: {e}")
                raise


def _extract_decision_sort_key(url: str):
    """Extract sort key from decision URL for ordering."""
    match = re.search(r'/dec-?(\d+)([a-z]?)-(\d{4})([a-z]?)', url)
    if match:
        year = int(match.group(3))
        decision_num = int(match.group(1))
        suffix_order = ord(match.group(2)) if match.group(2) else 0
        postfix_order = ord(match.group(4)) if match.group(4) else 0
        return (-year, -decision_num, -suffix_order, -postfix_order)
    return (0, 0, 0, 0)


def extract_decision_urls_from_catalog_selenium(max_decisions: int = 5, swd=None) -> List[Dict]:
    """
    Use Selenium to call the gov.il REST API and extract decision entries.

    The catalog page is an SPA that loads data from a JSON API.
    We call the API directly via Selenium (to pass Cloudflare) and
    parse the structured JSON response, returning metadata dicts.

    Args:
        max_decisions: Maximum number of decision entries to extract
        swd: Optional SeleniumWebDriver instance to reuse (avoids creating new Chrome)

    Returns:
        List of dicts with keys: url, title, decision_number, decision_date, committee
    """
    logger.info(f"Using Selenium to extract {max_decisions} decision entries from catalog")

    api_url = f"{CATALOG_API_URL}&skip=0&limit={max_decisions}"

    def _fetch_catalog(driver_instance, retry_count=0):
        drv = driver_instance.driver
        max_retries = 2

        try:
            # First visit the main page to establish a "legitimate" session
            if retry_count == 0:
                logger.info("Visiting main gov.il page first to establish session...")
                drv.get("https://www.gov.il/he")
                time.sleep(5)

            logger.info(f"Loading catalog API: {api_url}")
            if swd:
                # Use navigate_to for rate-limited navigation in reused session
                driver_instance.navigate_to(api_url, wait_time=8)
            else:
                drv.get(api_url)
                time.sleep(8)

            body = drv.find_element(By.TAG_NAME, "body").text

            if not body or not body.startswith("{"):
                logger.warning(f"API returned non-JSON response (length={len(body)}). Retrying after loading main page first...")
                if swd:
                    driver_instance.navigate_to("https://www.gov.il/he/collectors/policies", wait_time=10)
                    driver_instance.navigate_to(api_url, wait_time=8)
                else:
                    drv.get("https://www.gov.il/he/collectors/policies")
                    time.sleep(10)
                    drv.get(api_url)
                    time.sleep(8)
                body = drv.find_element(By.TAG_NAME, "body").text

            return body

        except CloudflareBlockedError as e:
            if retry_count < max_retries:
                wait_time = 30 * (retry_count + 1)  # 30s, 60s
                logger.warning(f"Cloudflare block detected. Waiting {wait_time}s and retrying... (attempt {retry_count + 1}/{max_retries})")
                time.sleep(wait_time)
                # Navigate to main catalog page first
                drv.get("https://www.gov.il/he/collectors/policies")
                time.sleep(15)
                return _fetch_catalog(driver_instance, retry_count + 1)
            else:
                raise

    try:
        if swd:
            body = _fetch_catalog(swd)
        else:
            with SeleniumWebDriver(headless=True) as new_swd:
                body = _fetch_catalog(new_swd)

        if not body or not body.startswith("{"):
            logger.error(f"API still returned non-JSON after retry. Body: {body[:200]}")
            return []

        data = json.loads(body)
        total = data.get("total", 0)
        results = data.get("results", [])

        logger.info(f"API returned {len(results)} results (total available: {total})")

        # Extract decision entries with metadata from API results using the new function
        decision_entries = []
        for result in results:
            entry = extract_entry_from_api_result(result)
            if entry:
                decision_entries.append(entry)

        # Sort by decision number (newest first)
        decision_entries.sort(key=lambda d: _extract_decision_sort_key(d["url"]))

        logger.info(f"Sorted {len(decision_entries)} entries by decision number (newest first)")

        if not decision_entries:
            logger.warning("No decision entries found from API!")

        logger.info(f"Extracted {len(decision_entries)} decision entries")
        for i, entry in enumerate(decision_entries, 1):
            logger.info(f"  {i}. {entry['url']} | #{entry['decision_number']} | {entry['decision_date']}")

        return decision_entries

    except Exception as e:
        logger.error(f"Failed to extract decision entries with Selenium: {e}")
        raise


def paginate_full_catalog(driver_instance, page_size: int = 50, start_skip: int = 0, callback=None):
    """
    Paginate through the full government decisions catalog with proper pagination.

    Loops through all pages using skip/limit, calls extract_entry_from_api_result()
    on each result, and yields complete metadata for each decision. Handles
    pagination properly with delays.

    Args:
        driver_instance: SeleniumWebDriver instance to use
        page_size: Number of results per page (default 50)
        start_skip: Starting skip value for pagination (default 0)
        callback: Optional callback function to call for each yielded entry

    Yields:
        Complete decision metadata dict for each decision
    """
    current_skip = start_skip
    total_processed = 0

    logger.info(f"Starting full catalog pagination with page_size={page_size}, start_skip={start_skip}")

    while True:
        api_url = f"{CATALOG_API_URL}&skip={current_skip}&limit={page_size}"
        logger.info(f"Fetching page: skip={current_skip}, limit={page_size}")

        try:
            # Navigate to API endpoint with rate limiting
            driver_instance.navigate_to(api_url, wait_time=8)

            # Get the JSON response
            body = driver_instance.driver.find_element(By.TAG_NAME, "body").text

            if not body or not body.startswith("{"):
                logger.warning(f"Non-JSON response received, stopping pagination")
                break

            data = json.loads(body)
            results = data.get("results", [])
            total_available = data.get("total", 0)

            if not results:
                logger.info("No more results available, stopping pagination")
                break

            logger.info(f"Processing {len(results)} results from page (total available: {total_available})")

            # Process each result and yield complete metadata
            for result in results:
                entry = extract_entry_from_api_result(result)
                if entry:
                    total_processed += 1
                    if callback:
                        callback(entry)
                    yield entry

            # Check if we've reached the end
            if len(results) < page_size or current_skip + len(results) >= total_available:
                logger.info(f"Reached end of catalog. Total processed: {total_processed}")
                break

            # Move to next page
            current_skip += page_size

            # Add delay between pages to avoid rate limiting
            time.sleep(2)

        except Exception as e:
            logger.error(f"Error during pagination at skip={current_skip}: {e}")
            break

    logger.info(f"Full catalog pagination completed. Total entries processed: {total_processed}")


def find_correct_url_in_catalog(decision_number: str, max_search_decisions: int = 100, swd=None) -> Optional[str]:
    """
    Search the catalog for the correct URL for a given decision number.
    This is used when a URL fails and we need to find the actual working URL.

    Args:
        decision_number: The decision number to search for (e.g., "3173")
        max_search_decisions: How many decisions to search through
        swd: Optional SeleniumWebDriver instance to reuse

    Returns:
        The correct URL if found, None otherwise
    """
    logger.info(f"Searching catalog for correct URL for decision {decision_number}")

    try:
        catalog_entries = extract_decision_urls_from_catalog_selenium(max_decisions=max_search_decisions, swd=swd)

        possible_urls = []
        for entry in catalog_entries:
            match = re.search(r'/dec-?(\d+)([a-z]?)-(\d{4})([a-z]?)', entry["url"])
            if match and match.group(1) == decision_number:
                possible_urls.append(entry["url"])

        if possible_urls:
            logger.info(f"Found {len(possible_urls)} possible URLs for decision {decision_number}: {possible_urls}")
            return possible_urls[0]
        else:
            logger.warning(f"No URLs found in catalog for decision {decision_number}")
            return None

    except Exception as e:
        logger.error(f"Failed to search catalog for decision {decision_number}: {e}")
        return None


def try_url_variations(base_url: str, decision_number: str, swd=None) -> Optional[str]:
    """
    Try URL variations when catalog search fails.
    Tries common suffix patterns: a, b, c and hyphen variations.

    Args:
        base_url: The original URL that failed
        decision_number: The decision number
        swd: Optional SeleniumWebDriver instance to reuse

    Returns:
        Working URL if found, None otherwise
    """
    logger.info(f"Trying URL variations for decision {decision_number}")

    # Extract base components - support both dec3173 and dec-3173 formats
    match = re.search(r'(https?://[^/]+/he/pages/)(dec-?)(\d+)(-\d{4})', base_url)
    if not match:
        return None

    domain, dec_prefix, num, year_suffix = match.groups()

    # Expanded patterns: a, b, c suffixes
    letter_suffixes = ['a', 'b', 'c']
    variations = []

    for s in letter_suffixes:
        # dec3173a-2025, dec3173b-2025
        variations.append(f"{domain}{dec_prefix}{num}{s}{year_suffix}")
        # dec3173-2025a, dec3173-2025b
        variations.append(f"{domain}{dec_prefix}{num}{year_suffix}{s}")

    # Add hyphen variations if original didn't have hyphen
    if dec_prefix == 'dec':
        for s in letter_suffixes:
            # dec-3173a-2025
            variations.append(f"{domain}dec-{num}{s}{year_suffix}")
            # dec-3173-2025a
            variations.append(f"{domain}dec-{num}{year_suffix}{s}")

    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique_variations.append(v)

    for variation_url in unique_variations:
        try:
            logger.info(f"Testing URL variation: {variation_url}")
            if swd:
                soup = swd.navigate_to(variation_url, wait_time=5)
            else:
                with SeleniumWebDriver(headless=True) as driver:
                    soup = driver.get_page_with_js(variation_url, wait_time=5)
            content = soup.get_text()

            if len(content) > 200 and any(char > '\u0590' for char in content):
                logger.info(f"Found working URL variation: {variation_url}")
                return variation_url

        except Exception as e:
            logger.debug(f"URL variation {variation_url} failed: {e}")
            continue

    logger.warning(f"No working URL variations found for decision {decision_number}")
    return None


def test_parse_government_field():
    """Test the parse_government_field function with sample inputs (Checkpoint 2a)."""
    print("🧪 Testing parse_government_field function...")

    test_cases = [
        ("הממשלה ה- 37", ("37", None)),
        ("הממשלה ה- 25, יצחק רבין", ("25", "יצחק רבין")),
        ("ממשלה 32", ("32", None)),
        ("הממשלה ה- 36, נפתלי בנט", ("36", "נפתלי בנט")),
        ("", (None, None)),
        (None, (None, None)),
        ("לא קיים מספר", (None, None)),
    ]

    all_passed = True
    for i, (input_text, expected) in enumerate(test_cases, 1):
        try:
            result = parse_government_field(input_text)
            if result == expected:
                print(f"✅ Test {i}: '{input_text}' → {result}")
            else:
                print(f"❌ Test {i}: '{input_text}' → {result} (expected {expected})")
                all_passed = False
        except Exception as e:
            print(f"❌ Test {i}: '{input_text}' → Exception: {e}")
            all_passed = False

    return all_passed


def test_extract_entry_from_api_result():
    """Test the extract_entry_from_api_result function with sample API data (Checkpoint 2b)."""
    print("🧪 Testing extract_entry_from_api_result function...")

    # Sample API result structure (based on actual gov.il API format)
    sample_api_result = {
        "url": "/he/pages/dec3173-2025",
        "title": "החלטה בדבר מדיניות כלכלית חדשה",
        "description": "תיאור ההחלטה הממשלתית",
        "tags": {
            "promotedMetaData": {
                "מספר החלטה": [{"title": "3173"}]
            },
            "metaData": {
                "תאריך פרסום": [{"title": "15.01.2025"}],
                "ועדות שרים": [{"title": "ועדת שרים לענייני בריאות"}],
                "ממשלה": [{"title": "הממשלה ה- 37"}]
            }
        }
    }

    try:
        result = extract_entry_from_api_result(sample_api_result)

        if result:
            print("✅ Successfully extracted entry:")
            for key, value in result.items():
                if key != 'raw_api_result':  # Skip large debug object
                    print(f"   {key}: {value}")

            # Verify expected fields
            expected_fields = ['url', 'title', 'decision_number', 'decision_date',
                             'government_number', 'prime_minister', 'committee', 'description']
            missing_fields = [f for f in expected_fields if f not in result]
            if missing_fields:
                print(f"❌ Missing fields: {missing_fields}")
                return False

            # Verify date format conversion
            if result['decision_date'] != '2025-01-15':
                print(f"❌ Date conversion failed: expected '2025-01-15', got '{result['decision_date']}'")
                return False

            # Verify government number extraction
            if result['government_number'] != '37':
                print(f"❌ Government number extraction failed: expected '37', got '{result['government_number']}'")
                return False

            # Verify PM lookup worked
            if result['prime_minister'] != 'בנימין נתניהו':
                print(f"❌ PM lookup failed: expected 'בנימין נתניהו', got '{result['prime_minister']}'")
                return False

            print("✅ All field validations passed")
            return True
        else:
            print("❌ Function returned None")
            return False

    except Exception as e:
        print(f"❌ Function failed with exception: {e}")
        return False


def test_catalog_scraping():
    """Test the Selenium-based catalog scraping."""
    try:
        logger.info("Testing Selenium-based catalog scraping...")
        entries = extract_decision_urls_from_catalog_selenium(3)

        if entries:
            print(f"✅ Found {len(entries)} decision entries:")
            for i, entry in enumerate(entries, 1):
                print(f"   {i}. #{entry['decision_number']} | {entry['decision_date']} | {entry['title'][:60]}")
            return True
        else:
            print("❌ No decision entries found")
            return False

    except Exception as e:
        print(f"❌ Catalog scraping failed: {e}")
        return False


def run_checkpoint_tests():
    """Run Checkpoint 2a and 2b verification tests."""
    print("=" * 60)
    print("CHECKPOINT 2a & 2b VERIFICATION TESTS")
    print("=" * 60)

    print("\n🔍 Checkpoint 2a: Testing parse_government_field()")
    test_2a_passed = test_parse_government_field()

    print("\n🔍 Checkpoint 2b: Testing extract_entry_from_api_result()")
    test_2b_passed = test_extract_entry_from_api_result()

    print("\n" + "=" * 60)
    print("CHECKPOINT TEST RESULTS:")
    print(f"Checkpoint 2a (parse_government_field): {'✅ PASSED' if test_2a_passed else '❌ FAILED'}")
    print(f"Checkpoint 2b (extract_entry_from_api_result): {'✅ PASSED' if test_2b_passed else '❌ FAILED'}")

    overall_success = test_2a_passed and test_2b_passed
    print(f"Overall Status: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    print("=" * 60)

    return overall_success


if __name__ == "__main__":
    # Run checkpoint verification tests first
    checkpoint_success = run_checkpoint_tests()

    if checkpoint_success:
        print("\n🚀 Running integration test...")
        test_catalog_scraping()
    else:
        print("\n⚠️ Checkpoint tests failed - skipping integration test")