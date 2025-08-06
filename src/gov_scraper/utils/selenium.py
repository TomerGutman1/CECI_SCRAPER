"""Selenium WebDriver utilities for JavaScript-rendered content."""

import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from ..config import CHROME_BINARY

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SeleniumWebDriver:
    """WebDriver wrapper for scraping JavaScript-rendered content."""
    
    def __init__(self, headless=True, timeout=30):
        """
        Initialize WebDriver with Chrome.
        
        Args:
            headless: Run in headless mode (no GUI)
            timeout: Default timeout for page loads
        """
        self.timeout = timeout
        self.driver: webdriver.Chrome
        
        try:
            # Set up Chrome options
            chrome_options = Options()
            
            if headless:
                chrome_options.add_argument('--headless')

            # Additional options for stability
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument(f"--binary-location={CHROME_BINARY}")
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            
            # Initialize ChromeDriver
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(timeout)
            
            logger.info("Chrome WebDriver initialized successfully")
            
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
                # Wait for specific element
                try:
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
                    )
                    logger.info(f"Found expected element: {wait_for_element}")
                except TimeoutException:
                    logger.warning(f"Timeout waiting for element: {wait_for_element}")
            else:
                # General wait for page to load
                time.sleep(wait_time)
            
            # Get the rendered HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            logger.info(f"Page loaded successfully, HTML length: {len(html)}")
            return soup
            
        except Exception as e:
            logger.error(f"Failed to load page {url}: {e}")
            raise
    
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
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    href = 'https://www.gov.il' + href
                links.append(href)
        
        return list(set(links))  # Remove duplicates
    
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
            # Test with a simple page
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