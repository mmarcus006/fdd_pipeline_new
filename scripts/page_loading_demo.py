#!/usr/bin/env python3
"""
Page Loading Detection Demo
===========================

This script demonstrates various methods to check if a Chrome window
has finished loading using the Selenium template with page loading detection.

Methods demonstrated:
1. wait_for_page_load_complete() - Comprehensive check
2. is_page_loaded() - Quick status check
3. wait_for_ajax_complete() - AJAX specific
4. wait_for_element_stable() - Element animation check
5. wait_for_angular_ready() - Angular apps
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import selenium_template_antibot
sys.path.append(str(Path(__file__).parent))

from selenium_template_antibot import AntiBotSeleniumTemplate
import time


def demonstrate_page_loading():
    """Demonstrate various page loading detection methods."""
    
    # Initialize Chrome driver
    print("Initializing Chrome driver...")
    scraper = AntiBotSeleniumTemplate(browser="chrome", headless=False)
    
    try:
        # Example 1: Navigate with automatic page load waiting
        print("\n" + "="*50)
        print("Example 1: Navigate with automatic page load waiting")
        print("="*50)
        
        url = "https://www.example.com"
        print(f"Navigating to {url}...")
        
        # This will automatically wait for the page to load
        if scraper.navigate_to_url(url, wait_for_load=True):
            print("✅ Page loaded successfully!")
            print(f"Current URL: {scraper.get_current_url()}")
            print(f"Page Title: {scraper.get_page_title()}")
        
        # Example 2: Quick check if page is loaded
        print("\n" + "="*50)
        print("Example 2: Quick page load status check")
        print("="*50)
        
        if scraper.is_page_loaded():
            print("✅ Page is fully loaded")
        else:
            print("⏳ Page is still loading...")
        
        # Example 3: Navigate to a more complex page with AJAX
        print("\n" + "="*50)
        print("Example 3: Navigate to page with potential AJAX")
        print("="*50)
        
        ajax_url = "https://www.google.com"
        print(f"Navigating to {ajax_url}...")
        
        # Navigate without automatic waiting
        scraper.driver.get(ajax_url)
        
        # Manually wait for page load
        print("Waiting for page to complete loading...")
        if scraper.wait_for_page_load_complete(timeout=15):
            print("✅ Page load complete")
        
        # Check for AJAX completion
        print("Checking for AJAX requests...")
        if scraper.wait_for_ajax_complete(timeout=10):
            print("✅ All AJAX requests completed (or no jQuery detected)")
        
        # Example 4: Wait for a specific element to be stable
        print("\n" + "="*50)
        print("Example 4: Wait for element stability")
        print("="*50)
        
        # Find the Google search box
        search_box = scraper.find_element_by_name("q")
        if search_box:
            print("Found search box element")
            if scraper.wait_for_element_stable(search_box, timeout=5):
                print("✅ Search box element is stable (not animating)")
        
        # Example 5: Demonstrate page loading during navigation
        print("\n" + "="*50)
        print("Example 5: Monitor page loading during navigation")
        print("="*50)
        
        # Type a search query
        if search_box:
            print("Typing search query...")
            scraper.type_in_element(search_box, "Selenium WebDriver")
            search_box.submit()
            
            print("Waiting for search results to load...")
            start_time = time.time()
            
            # Poll the page load status
            while not scraper.is_page_loaded() and (time.time() - start_time) < 10:
                print("⏳ Page loading...", end="\r")
                time.sleep(0.5)
            
            if scraper.is_page_loaded():
                print("✅ Search results loaded successfully!")
                print(f"Load time: {time.time() - start_time:.2f} seconds")
            else:
                print("⚠️ Page load timeout")
        
        # Example 6: Custom wait condition
        print("\n" + "="*50)
        print("Example 6: Custom wait for specific content")
        print("="*50)
        
        # Wait for specific text to appear
        from selenium.webdriver.common.by import By
        if scraper.wait_for_text_in_element((By.TAG_NAME, "body"), "Search", timeout=10):
            print("✅ Found 'Search' text on page")
        
        # Take a screenshot of the final state
        print("\n📸 Taking screenshot...")
        screenshot_file = scraper.take_screenshot("page_loading_demo.png")
        print(f"Screenshot saved: {screenshot_file}")
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
    
    finally:
        # Always close the browser
        print("\nClosing browser...")
        scraper.close_browser()
        print("Demo completed!")


def demonstrate_advanced_loading_scenarios():
    """Demonstrate more advanced loading scenarios."""
    
    scraper = AntiBotSeleniumTemplate(browser="chrome", headless=False)
    
    try:
        print("\n" + "="*50)
        print("Advanced Loading Scenarios")
        print("="*50)
        
        # Scenario 1: Page with lazy loading
        print("\n1. Handling lazy-loaded content:")
        scraper.navigate_to_url("https://unsplash.com", wait_for_load=True)
        
        # Scroll down to trigger lazy loading
        print("Scrolling to trigger lazy loading...")
        for i in range(3):
            scraper.scroll_page("down", 500)
            print(f"  Scroll {i+1}/3")
            
            # Wait for new content to load
            if scraper.wait_for_ajax_complete(timeout=5):
                print("  ✅ New content loaded")
            time.sleep(1)
        
        # Scenario 2: Single Page Application (SPA) navigation
        print("\n2. Handling SPA navigation:")
        print("(This would work on Angular/React sites)")
        
        # Check if Angular is present
        if scraper.wait_for_angular_ready(timeout=5):
            print("✅ Angular app ready (or not present)")
        
    except Exception as e:
        print(f"❌ Error in advanced scenarios: {e}")
    
    finally:
        scraper.close_browser()


if __name__ == "__main__":
    print("🚀 Starting Page Loading Detection Demo\n")
    
    # Run the main demonstration
    demonstrate_page_loading()
    
    # Uncomment to run advanced scenarios
    # print("\n" + "="*70)
    # demonstrate_advanced_loading_scenarios()
