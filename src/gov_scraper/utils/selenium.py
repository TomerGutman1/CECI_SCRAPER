"""Selenium WebDriver utilities for JavaScript-rendered content."""

import time
import random
import logging
import subprocess
from typing import Optional
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _detect_chrome_version():
    """Detect the installed Chrome major version."""
    import platform

    # macOS-specific detection
    if platform.system() == "Darwin":
        macos_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for path in macos_paths:
            try:
                output = subprocess.check_output([path, "--version"], stderr=subprocess.DEVNULL).decode().strip()
                # e.g. "Google Chrome 144.0.7559.133" → 144
                version_str = output.split()[-1]
                major = int(version_str.split(".")[0])
                logger.info(f"Detected Chrome version: {major} (from: {output})")
                return major
            except Exception:
                continue

    # Linux detection
    for cmd in ["google-chrome --version", "chromium --version", "chromium-browser --version"]:
        try:
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
            # e.g. "Google Chrome 144.0.7559.96" → 144
            version_str = output.split()[-1]
            major = int(version_str.split(".")[0])
            logger.info(f"Detected Chrome version: {major} (from: {output})")
            return major
        except Exception:
            continue
    logger.warning("Could not detect Chrome version, letting undetected-chromedriver auto-detect")
    return None


# Rate limiting constants to avoid Cloudflare WAF blocks
REQUEST_DELAY_MIN = 2.0   # seconds - minimum delay before each navigation
REQUEST_DELAY_MAX = 5.0   # seconds - maximum delay before each navigation

# Dynamic backoff constants
BACKOFF_INCREASE = 2.0    # Multiply delay by this on Cloudflare detection
BACKOFF_DECAY = 0.9       # Multiply by this on each successful navigation
BACKOFF_MAX = 4.0         # Cap multiplier (max effective delay = 5s * 4 = 20s)

# Fingerprint randomization pools
COMMON_RESOLUTIONS = [
    "1920,1080", "1366,768", "1536,864",
    "1440,900", "1280,720", "2560,1440",
]
ACCEPT_LANGUAGE_VARIANTS = [
    "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "he,en-US;q=0.9,en;q=0.8",
    "he-IL,he;q=0.8,en;q=0.5",
]

# Cloudflare detection patterns
CLOUDFLARE_TEXT_PATTERNS = [
    # JS challenge
    "just a moment",
    "checking your browser",
    "cf-browser-verification",
    "cf-challenge",
    # Block page
    "sorry you have been blocked",
    "access denied",
    "attention required",
    # Verification
    "verify you are human",
    "enable javascript and cookies",
    # Rate limit / WAF
    "ray id:",
    "too many requests",
    "rate limit",
]
CLOUDFLARE_TITLE_PATTERNS = [
    "just a moment",
    "attention required",
    "access denied",
]


class CloudflareBlockedError(Exception):
    """Raised when Cloudflare challenge or block page is detected."""
    pass


def detect_cloudflare_block(soup: BeautifulSoup) -> Optional[str]:
    """
    Check if a page is a Cloudflare challenge/block page.

    Args:
        soup: BeautifulSoup object of the loaded page

    Returns:
        Block reason string if Cloudflare detected, None otherwise
    """
    if soup is None:
        return "empty page (no soup)"

    page_text = soup.get_text(separator=" ", strip=True).lower()
    page_title = (soup.title.string or "").lower() if soup.title else ""

    # Check title patterns
    for pattern in CLOUDFLARE_TITLE_PATTERNS:
        if pattern in page_title:
            return f"Cloudflare title: '{soup.title.string}'"

    # Check text patterns
    for pattern in CLOUDFLARE_TEXT_PATTERNS:
        if pattern in page_text:
            return f"Cloudflare pattern: '{pattern}'"

    # Very short page with no Hebrew content — likely a block page
    has_hebrew = any('\u0590' <= char <= '\u05FF' for char in page_text)
    if len(page_text) < 200 and not has_hebrew and "cloudflare" in str(soup).lower():
        return "Short non-Hebrew page with Cloudflare reference"

    return None


class SeleniumWebDriver:
    """WebDriver wrapper using undetected-chromedriver to bypass Cloudflare."""

    def __init__(self, headless=True, timeout=30):
        """
        Initialize WebDriver with undetected Chrome and randomized fingerprint.

        Args:
            headless: Run in headless mode (no GUI)
            timeout: Default timeout for page loads
        """
        self.timeout = timeout
        self.driver = None
        self.delay_multiplier = 1.0  # Dynamic backoff multiplier

        try:
            options = uc.ChromeOptions()

            if headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')

            # Randomized fingerprint (per session)
            resolution = random.choice(COMMON_RESOLUTIONS)
            language = random.choice(ACCEPT_LANGUAGE_VARIANTS)
            options.add_argument(f'--window-size={resolution}')
            options.add_argument(f'--accept-language={language}')
            logger.info(f"Session fingerprint: resolution={resolution}, lang={language.split(',')[0]}")

            chrome_version = _detect_chrome_version()
            self.driver = uc.Chrome(options=options, version_main=chrome_version)
            self.driver.set_page_load_timeout(timeout)

            logger.info("Undetected Chrome WebDriver initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def get_page_with_js(self, url, wait_for_element=None, wait_time=10):
        """
        Load a page and wait for JavaScript to render content.

        Args:
            url: URL to load
            wait_for_element: CSS selector to wait for (optional)
            wait_time: Time to wait for element/content

        Returns:
            BeautifulSoup object with rendered HTML
        """
        try:
            logger.info(f"Loading page: {url}")
            self.driver.get(url)

            if wait_for_element:
                try:
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
                    )
                    logger.info(f"Found expected element: {wait_for_element}")
                except TimeoutException:
                    logger.warning(f"Timeout waiting for element: {wait_for_element}")
            else:
                time.sleep(wait_time)

            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            logger.info(f"Page loaded successfully, HTML length: {len(html)}")
            return soup

        except Exception as e:
            logger.error(f"Failed to load page {url}: {e}")
            raise

    def navigate_to(self, url, wait_time=10):
        """
        Navigate to a new URL in the existing session with rate limiting
        and Cloudflare detection.

        Uses dynamic backoff: delays increase after Cloudflare detection
        and decay back to normal after successful navigations.

        Args:
            url: URL to navigate to
            wait_time: Time to wait for page to render

        Returns:
            BeautifulSoup object with rendered HTML

        Raises:
            CloudflareBlockedError: If Cloudflare challenge/block page detected
        """
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX) * self.delay_multiplier
        if self.delay_multiplier > 1.0:
            logger.info(f"Rate limit: waiting {delay:.1f}s (multiplier={self.delay_multiplier:.1f}x)")
        else:
            logger.debug(f"Rate limit: waiting {delay:.1f}s before navigation")
        time.sleep(delay)

        logger.info(f"Navigating to: {url}")
        self.driver.get(url)
        time.sleep(wait_time)
        html = self.driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        logger.info(f"Page loaded, HTML length: {len(html)}")

        # Check for Cloudflare block
        block_reason = detect_cloudflare_block(soup)
        if block_reason:
            self.delay_multiplier = min(self.delay_multiplier * BACKOFF_INCREASE, BACKOFF_MAX)
            logger.warning(f"Cloudflare detected: {block_reason}. Backoff multiplier → {self.delay_multiplier:.1f}x")
            raise CloudflareBlockedError(block_reason)

        # Success — decay multiplier toward 1.0
        if self.delay_multiplier > 1.0:
            self.delay_multiplier = max(1.0, self.delay_multiplier * BACKOFF_DECAY)
            logger.debug(f"Backoff decay → {self.delay_multiplier:.2f}x")

        return soup

    def find_links_with_pattern(self, soup, pattern):
        """
        Find all links matching a regex pattern.

        Args:
            soup: BeautifulSoup object
            pattern: Regex pattern to match

        Returns:
            List of matching URLs
        """
        import re

        links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if re.search(pattern, href):
                if href.startswith('/'):
                    href = 'https://www.gov.il' + href
                links.append(href)

        return list(set(links))

    def wait_for_content_with_text(self, text_to_find, max_wait=15):
        """
        Wait for page to load content containing specific text.

        Args:
            text_to_find: Text to search for in page content
            max_wait: Maximum time to wait

        Returns:
            True if text found, False otherwise
        """
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                if text_to_find in self.driver.page_source:
                    logger.info(f"Found expected text: {text_to_find}")
                    return True
                time.sleep(1)
            except Exception:
                pass

        logger.warning(f"Timeout waiting for text: {text_to_find}")
        return False

    def close(self):
        """Close the WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def test_selenium_setup():
    """Test function to verify Selenium is working."""
    try:
        with SeleniumWebDriver(headless=True) as driver:
            soup = driver.get_page_with_js('https://www.google.com', wait_time=5)

            if soup and len(soup.get_text()) > 100:
                print("✅ Selenium setup successful!")
                print(f"   Page title: {soup.title.string if soup.title else 'No title'}")
                return True
            else:
                print("❌ Selenium setup failed - no content loaded")
                return False

    except Exception as e:
        print(f"❌ Selenium setup failed: {e}")
        return False


if __name__ == "__main__":
    test_selenium_setup()
