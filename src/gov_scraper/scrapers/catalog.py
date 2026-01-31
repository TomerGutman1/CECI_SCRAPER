"""Selenium-based scraper for the Israeli Government decisions catalog page."""

import json
import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from ..utils.selenium import SeleniumWebDriver
from ..config import BASE_CATALOG_URL, CATALOG_PARAMS, BASE_DECISION_URL

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


def extract_decision_urls_from_catalog_selenium(max_decisions: int = 5) -> List[Dict]:
    """
    Use Selenium to call the gov.il REST API and extract decision entries.

    The catalog page is an SPA that loads data from a JSON API.
    We call the API directly via Selenium (to pass Cloudflare) and
    parse the structured JSON response, returning metadata dicts.

    Args:
        max_decisions: Maximum number of decision entries to extract

    Returns:
        List of dicts with keys: url, title, decision_number, decision_date, committee
    """
    logger.info(f"Using Selenium to extract {max_decisions} decision entries from catalog")

    api_url = f"{CATALOG_API_URL}&skip=0&limit={max_decisions}"

    try:
        with SeleniumWebDriver(headless=True) as swd:
            drv = swd.driver

            logger.info(f"Loading catalog API: {api_url}")
            drv.get(api_url)
            time.sleep(8)

            body = drv.find_element(By.TAG_NAME, "body").text

            if not body or not body.startswith("{"):
                logger.warning(f"API returned non-JSON response (length={len(body)}). Retrying after loading main page first...")
                drv.get("https://www.gov.il/he/collectors/policies")
                time.sleep(10)
                drv.get(api_url)
                time.sleep(8)
                body = drv.find_element(By.TAG_NAME, "body").text

            if not body or not body.startswith("{"):
                logger.error(f"API still returned non-JSON after retry. Body: {body[:200]}")
                return []

            data = json.loads(body)
            total = data.get("total", 0)
            results = data.get("results", [])

            logger.info(f"API returned {len(results)} results (total available: {total})")

            # Extract decision entries with metadata from API results
            decision_entries = []
            for result in results:
                url_path = result.get("url", "")
                if not url_path or not re.search(r'/he/pages/dec-?\d+', url_path):
                    continue

                full_url = f"{BASE_DECISION_URL}{url_path}"
                title = result.get("title", "")

                # Extract metadata from structured tags
                tags = result.get("tags", {})
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

                decision_entries.append({
                    "url": full_url,
                    "title": title,
                    "decision_number": decision_number,
                    "decision_date": decision_date,
                    "committee": committee,
                })

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
        catalog_entries = extract_decision_urls_from_catalog_selenium(max_decisions=max_search_decisions)

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

    # Extract base components - support both dec3173 and dec-3173 formats
    match = re.search(r'(https?://[^/]+/he/pages/dec-?)(\d+)(-\d{4})', base_url)
    if not match:
        return None

    prefix, num, suffix = match.groups()

    variations = [
        f"{prefix}{num}a{suffix}",   # dec3173a-2025 or dec-3173a-2025
        f"{prefix}{num}{suffix}a"    # dec3173-2025a or dec-3173-2025a
    ]

    for variation_url in variations:
        try:
            logger.info(f"Testing URL variation: {variation_url}")
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


if __name__ == "__main__":
    test_catalog_scraping()