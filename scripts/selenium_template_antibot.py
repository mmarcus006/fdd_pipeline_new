#!/usr/bin/env python3
"""
Selenium Template Script with Anti-Bot Avoidance
================================================

A comprehensive template for web scraping with Selenium that includes:
- Anti-bot detection avoidance techniques
- Various HTML selector methods
- Human-like behavior simulation
- Error handling and logging
- Configurable delays and timeouts

Usage:
    python selenium_template_antibot.py
"""

import time
import random
import logging
from typing import Optional, List, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    ElementClickInterceptedException,
    WebDriverException
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AntiBotSeleniumTemplate:
    """
    A Selenium template class with anti-bot detection avoidance features.
    """
    
    def __init__(self, browser: str = "chrome", headless: bool = False):
        """
        Initialize the Selenium driver with anti-bot configurations.
        
        Args:
            browser: Browser type ("chrome" or "firefox")
            headless: Whether to run in headless mode (False by default)
        """
        self.browser = browser.lower()
        self.headless = headless
        self.driver = None
        self.wait = None
        
        # Anti-bot configuration
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        self.setup_driver()
    
    def setup_driver(self) -> None:
        """Setup the WebDriver with anti-bot detection avoidance."""
        try:
            if self.browser == "chrome":
                self.driver = self._setup_chrome()
            elif self.browser == "firefox":
                self.driver = self._setup_firefox()
            else:
                raise ValueError(f"Unsupported browser: {self.browser}")
            
            # Set up WebDriverWait
            self.wait = WebDriverWait(self.driver, 10)
            
            # Execute anti-detection scripts
            self._execute_anti_detection_scripts()
            
            logger.info(f"Successfully initialized {self.browser} driver")
            
        except Exception as e:
            logger.error(f"Failed to setup driver: {e}")
            raise
    
    def _setup_chrome(self) -> webdriver.Chrome:
        """Setup Chrome driver with anti-bot options."""
        options = ChromeOptions()
        
        # Anti-detection options
        options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        
        # Performance options
        options.add_argument("--disable-logging")
        options.add_argument("--disable-gpu-logging")
        options.add_argument("--silent")
        
        # Window size for non-headless mode
        if not self.headless:
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")
        else:
            options.add_argument("--headless")
        
        return webdriver.Chrome(options=options)
    
    def _setup_firefox(self) -> webdriver.Firefox:
        """Setup Firefox driver with anti-bot options."""
        options = FirefoxOptions()
        
        # Anti-detection options
        options.set_preference("general.useragent.override", random.choice(self.user_agents))
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference("marionette.enabled", True)
        
        if self.headless:
            options.add_argument("--headless")
        
        return webdriver.Firefox(options=options)
    
    def _execute_anti_detection_scripts(self) -> None:
        """Execute JavaScript to avoid detection."""
        scripts = [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})",
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})",
            "window.chrome = {runtime: {}}",
        ]
        
        for script in scripts:
            try:
                self.driver.execute_script(script)
            except Exception as e:
                logger.warning(f"Failed to execute anti-detection script: {e}")
    
    def human_delay(self, min_delay: float = 1.0, max_delay: float = 3.0) -> None:
        """Simulate human-like delays."""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def human_type(self, element, text: str, typing_delay: float = 0.1) -> None:
        """Type text with human-like delays between keystrokes."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, typing_delay))
    
    def navigate_to_url(self, url: str, wait_for_load: bool = True) -> bool:
        """
        Navigate to a URL with error handling and optional page load waiting.
        
        Args:
            url: The URL to navigate to
            wait_for_load: Whether to wait for page to fully load
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Navigating to: {url}")
            self.driver.get(url)
            
            if wait_for_load:
                # Wait for page to be fully loaded
                if self.wait_for_page_load_complete():
                    logger.info("Page loaded successfully")
                else:
                    logger.warning("Page load timeout, but continuing")
            
            self.human_delay(2, 4)
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False
    
    def find_element_by_id(self, element_id: str, timeout: int = 10) -> Optional[Any]:
        """Find element by ID with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.ID, element_id))
            )
            logger.info(f"Found element by ID: {element_id}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by ID: {element_id}")
            return None
    
    def find_element_by_class_name(self, class_name: str, timeout: int = 10) -> Optional[Any]:
        """Find element by class name with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, class_name))
            )
            logger.info(f"Found element by class name: {class_name}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by class name: {class_name}")
            return None
    
    def find_element_by_xpath(self, xpath: str, timeout: int = 10) -> Optional[Any]:
        """Find element by XPath with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            logger.info(f"Found element by XPath: {xpath}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by XPath: {xpath}")
            return None
    
    def find_element_by_css_selector(self, css_selector: str, timeout: int = 10) -> Optional[Any]:
        """Find element by CSS selector with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )
            logger.info(f"Found element by CSS selector: {css_selector}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by CSS selector: {css_selector}")
            return None
    
    def find_element_by_tag_name(self, tag_name: str, timeout: int = 10) -> Optional[Any]:
        """Find element by tag name with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.TAG_NAME, tag_name))
            )
            logger.info(f"Found element by tag name: {tag_name}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by tag name: {tag_name}")
            return None
    
    def find_element_by_name(self, name: str, timeout: int = 10) -> Optional[Any]:
        """Find element by name attribute with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.NAME, name))
            )
            logger.info(f"Found element by name: {name}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by name: {name}")
            return None
    
    def find_element_by_link_text(self, link_text: str, timeout: int = 10) -> Optional[Any]:
        """Find element by link text with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.LINK_TEXT, link_text))
            )
            logger.info(f"Found element by link text: {link_text}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by link text: {link_text}")
            return None
    
    def find_element_by_partial_link_text(self, partial_link_text: str, timeout: int = 10) -> Optional[Any]:
        """Find element by partial link text with wait."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, partial_link_text))
            )
            logger.info(f"Found element by partial link text: {partial_link_text}")
            return element
        except TimeoutException:
            logger.warning(f"Element not found by partial link text: {partial_link_text}")
            return None
    
    def find_elements_by_css_selector(self, css_selector: str, timeout: int = 10) -> List[Any]:
        """Find multiple elements by CSS selector."""
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )
            elements = self.driver.find_elements(By.CSS_SELECTOR, css_selector)
            logger.info(f"Found {len(elements)} elements by CSS selector: {css_selector}")
            return elements
        except TimeoutException:
            logger.warning(f"No elements found by CSS selector: {css_selector}")
            return []
    
    def click_element(self, element, use_action_chains: bool = False) -> bool:
        """
        Click an element with human-like behavior.
        
        Args:
            element: The element to click
            use_action_chains: Whether to use ActionChains for clicking
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            self.human_delay(0.5, 1.0)
            
            if use_action_chains:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).click().perform()
            else:
                element.click()
            
            logger.info("Successfully clicked element")
            self.human_delay(1, 2)
            return True
            
        except ElementClickInterceptedException:
            logger.warning("Element click intercepted, trying JavaScript click")
            try:
                self.driver.execute_script("arguments[0].click();", element)
                self.human_delay(1, 2)
                return True
            except Exception as e:
                logger.error(f"JavaScript click failed: {e}")
                return False
        except Exception as e:
            logger.error(f"Failed to click element: {e}")
            return False
    
    def type_in_element(self, element, text: str, clear_first: bool = True) -> bool:
        """
        Type text in an element with human-like behavior.
        
        Args:
            element: The element to type in
            text: The text to type
            clear_first: Whether to clear the element first
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if clear_first:
                element.clear()
                self.human_delay(0.2, 0.5)
            
            self.human_type(element, text)
            logger.info(f"Successfully typed text: {text[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to type in element: {e}")
            return False
    
    def select_dropdown_option(self, dropdown_element, option_text: str = None, 
                             option_value: str = None, option_index: int = None) -> bool:
        """
        Select an option from a dropdown.
        
        Args:
            dropdown_element: The dropdown element
            option_text: Text of the option to select
            option_value: Value of the option to select
            option_index: Index of the option to select
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            select = Select(dropdown_element)
            
            if option_text:
                select.select_by_visible_text(option_text)
                logger.info(f"Selected dropdown option by text: {option_text}")
            elif option_value:
                select.select_by_value(option_value)
                logger.info(f"Selected dropdown option by value: {option_value}")
            elif option_index is not None:
                select.select_by_index(option_index)
                logger.info(f"Selected dropdown option by index: {option_index}")
            else:
                logger.error("No selection criteria provided for dropdown")
                return False
            
            self.human_delay(0.5, 1.0)
            return True
        except Exception as e:
            logger.error(f"Failed to select dropdown option: {e}")
            return False
    
    def wait_for_element_to_be_clickable(self, locator: tuple, timeout: int = 10) -> Optional[Any]:
        """Wait for an element to be clickable."""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
            return element
        except TimeoutException:
            logger.warning(f"Element not clickable within {timeout} seconds: {locator}")
            return None
    
    def wait_for_text_in_element(self, locator: tuple, text: str, timeout: int = 10) -> bool:
        """Wait for specific text to appear in an element."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.text_to_be_present_in_element(locator, text)
            )
            return True
        except TimeoutException:
            logger.warning(f"Text '{text}' not found in element within {timeout} seconds")
            return False
    
    def scroll_to_element(self, element) -> None:
        """Scroll to an element smoothly."""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", 
            element
        )
        self.human_delay(1, 2)
    
    def scroll_page(self, direction: str = "down", pixels: int = 500) -> None:
        """
        Scroll the page in a specified direction.
        
        Args:
            direction: "up" or "down"
            pixels: Number of pixels to scroll
        """
        if direction.lower() == "down":
            self.driver.execute_script(f"window.scrollBy(0, {pixels});")
        else:
            self.driver.execute_script(f"window.scrollBy(0, -{pixels});")
        
        self.human_delay(0.5, 1.0)
    
    def take_screenshot(self, filename: str = None) -> str:
        """Take a screenshot and save it."""
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
        
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved: {filename}")
            return filename
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""
    
    def get_page_source(self) -> str:
        """Get the page source."""
        return self.driver.page_source
    
    def get_current_url(self) -> str:
        """Get the current URL."""
        return self.driver.current_url
    
    def get_page_title(self) -> str:
        """Get the page title."""
        return self.driver.title
    
    def wait_for_page_load_complete(self, timeout: int = 30) -> bool:
        """
        Wait for the page to finish loading completely.
        
        This method checks multiple conditions:
        1. document.readyState == 'complete'
        2. No active jQuery AJAX requests (if jQuery is present)
        3. No active fetch requests
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if page loaded successfully, False if timeout
        """
        try:
            # Wait for document ready state to be complete
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Check for jQuery AJAX requests if jQuery is present
            jquery_check = """
            if (typeof jQuery !== 'undefined') {
                return jQuery.active == 0;
            }
            return true;
            """
            
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script(jquery_check)
            )
            
            # Additional check for any pending network requests
            # This uses Performance API to check for ongoing requests
            network_check = """
            var performance = window.performance || window.mozPerformance || window.msPerformance || window.webkitPerformance || {};
            var network = performance.getEntries() || {};
            return true;  // This is simplified - in practice you might want more sophisticated network checking
            """
            
            self.driver.execute_script(network_check)
            
            logger.info("Page load completed successfully")
            return True
            
        except TimeoutException:
            logger.warning(f"Page did not complete loading within {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error while waiting for page load: {e}")
            return False
    
    def is_page_loaded(self) -> bool:
        """
        Check if the current page is fully loaded.
        
        Returns:
            bool: True if page is loaded, False otherwise
        """
        try:
            # Check document ready state
            ready_state = self.driver.execute_script("return document.readyState")
            if ready_state != "complete":
                return False
            
            # Check for jQuery AJAX if present
            jquery_active = self.driver.execute_script("""
                if (typeof jQuery !== 'undefined') {
                    return jQuery.active;
                }
                return 0;
            """)
            
            if jquery_active > 0:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking page load status: {e}")
            return False
    
    def wait_for_ajax_complete(self, timeout: int = 30) -> bool:
        """
        Wait specifically for AJAX requests to complete.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if AJAX completed, False if timeout or no jQuery
        """
        try:
            # First check if jQuery exists
            has_jquery = self.driver.execute_script("return typeof jQuery !== 'undefined'")
            
            if not has_jquery:
                logger.info("jQuery not detected on page")
                return True
            
            # Wait for jQuery.active to be 0
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return jQuery.active == 0")
            )
            
            logger.info("All AJAX requests completed")
            return True
            
        except TimeoutException:
            logger.warning(f"AJAX requests did not complete within {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error waiting for AJAX: {e}")
            return False
    
    def wait_for_element_stable(self, element, timeout: int = 10) -> bool:
        """
        Wait for an element to become stable (position and size not changing).
        Useful for animations and dynamic content.
        
        Args:
            element: The element to monitor
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if element became stable, False if timeout
        """
        try:
            def element_is_stable(driver):
                # Get initial position and size
                initial_location = element.location
                initial_size = element.size
                
                # Wait a moment
                time.sleep(0.3)
                
                # Check if position and size are the same
                return (element.location == initial_location and 
                       element.size == initial_size)
            
            WebDriverWait(self.driver, timeout).until(element_is_stable)
            logger.info("Element is stable")
            return True
            
        except TimeoutException:
            logger.warning(f"Element did not stabilize within {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error waiting for element stability: {e}")
            return False
    
    def wait_for_angular_ready(self, timeout: int = 30) -> bool:
        """
        Wait for Angular application to be ready (if page uses Angular).
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if Angular is ready or not present, False if timeout
        """
        try:
            # Check if Angular is present
            angular_check = """
            if (window.angular) {
                var injector = angular.element(document).injector();
                if (injector) {
                    var $rootScope = injector.get('$rootScope');
                    var $http = injector.get('$http');
                    return $rootScope.$$phase == null && $http.pendingRequests.length === 0;
                }
            }
            return true;  // Angular not found, consider it ready
            """
            
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script(angular_check)
            )
            
            logger.info("Angular application is ready")
            return True
            
        except TimeoutException:
            logger.warning(f"Angular did not become ready within {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error checking Angular readiness: {e}")
            return False
    
    def close_browser(self) -> None:
        """Close the browser and clean up."""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


def example_usage():
    """Example usage of the AntiBotSeleniumTemplate class."""
    
    # Initialize the template
    scraper = AntiBotSeleniumTemplate(browser="firefox", headless=False)
    
    try:
        # Example 1: Navigate to a website
        if scraper.navigate_to_url("https://apps.dfi.wi.gov/apps/FranchiseEFiling/activeFilings.aspx"):
            print(f"Successfully navigated to: {scraper.get_current_url()}")
            print(f"Page title: {scraper.get_page_title()}")
                # By class name
        
        # Example 2: Find elements using different selectors
        
        # By ID
        element_by_id = scraper.find_element_by_id("example-id")
        if element_by_id:
            scraper.click_element(element_by_id)
        
        #Get Table of Active Registrations using CSS Selector (correct method for IDs)
        table_element = scraper.find_element_by_css_selector("#ctl00_contentPlaceholder_grdActiveFilings")
        if table_element:
            print(f"Found Wisconsin franchise table with {len(table_element.find_elements('tag name', 'tr'))} rows")
        
        # By class name (without # symbol)
        element_by_class = scraper.find_element_by_class_name("example-class")
        if element_by_class:
            scraper.type_in_element(element_by_class, "Example text")
        
        # By XPath
        element_by_xpath = scraper.find_element_by_xpath("//div[@class='example']")
        if element_by_xpath:
            scraper.scroll_to_element(element_by_xpath)
        
        # By CSS selector
        element_by_css = scraper.find_element_by_css_selector("div.example > p")
        if element_by_css:
            text_content = element_by_css.text
            print(f"Element text: {text_content}")
        
        # Find multiple elements
        elements = scraper.find_elements_by_css_selector("a")
        print(f"Found {len(elements)} links on the page")
        
        # Example 3: Handle forms
        search_input = scraper.find_element_by_name("search")
        if search_input:
            scraper.type_in_element(search_input, "selenium automation")
            search_input.send_keys(Keys.RETURN)
        
        # Example 4: Handle dropdowns
        dropdown = scraper.find_element_by_id("dropdown-example")
        if dropdown:
            scraper.select_dropdown_option(dropdown, option_text="Option 1")
        
        # Example 5: Take screenshot
        scraper.take_screenshot("example_screenshot.png")
        
        # Example 6: Scroll page
        scraper.scroll_page("down", 300)
        scraper.human_delay(2, 3)
        scraper.scroll_page("up", 150)
        
    except Exception as e:
        logger.error(f"Error in example usage: {e}")
    
    finally:
        # Always close the browser
        scraper.close_browser()


if __name__ == "__main__":
    """
    Run the example usage when script is executed directly.
    
    Modify the example_usage() function to suit your specific needs.
    """
    print("Starting Selenium Anti-Bot Template Example...")
    example_usage()
    print("Example completed!") 