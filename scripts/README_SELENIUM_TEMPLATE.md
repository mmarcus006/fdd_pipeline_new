# Selenium Anti-Bot Template

A comprehensive Selenium template for web scraping with advanced anti-bot detection avoidance features.

## Features

### Anti-Bot Detection Avoidance
- **User Agent Rotation**: Random user agents from real browsers
- **JavaScript Execution**: Removes webdriver properties that bots typically have
- **Human-like Behavior**: Random delays, natural typing patterns
- **Browser Fingerprint Masking**: Disables automation indicators
- **Performance Optimizations**: Reduces resource usage and detection vectors

### Comprehensive Selector Support
- **By ID**: `find_element_by_id("element-id")`
- **By Class Name**: `find_element_by_class_name("class-name")`
- **By XPath**: `find_element_by_xpath("//div[@class='example']")`
- **By CSS Selector**: `find_element_by_css_selector("div.example > p")`
- **By Tag Name**: `find_element_by_tag_name("button")`
- **By Name Attribute**: `find_element_by_name("input-name")`
- **By Link Text**: `find_element_by_link_text("Click Here")`
- **By Partial Link Text**: `find_element_by_partial_link_text("Click")`

### Human-like Interactions
- **Smart Clicking**: Scrolls to element, uses ActionChains when needed
- **Human Typing**: Character-by-character typing with random delays
- **Dropdown Handling**: Select by text, value, or index
- **Form Interactions**: Complete form filling capabilities
- **Scrolling**: Smooth scrolling with configurable parameters

### Error Handling & Logging
- **Comprehensive Exception Handling**: Graceful failure recovery
- **Detailed Logging**: Track all actions and errors
- **Screenshot Capture**: Automatic screenshots for debugging
- **Timeout Management**: Configurable wait times for elements

## Installation

### Prerequisites
You need to have Chrome or Firefox installed on your system, along with the corresponding WebDriver.

#### For Chrome:
1. Download ChromeDriver from: https://chromedriver.chromium.org/
2. Ensure ChromeDriver is in your PATH or specify the path in the script

#### For Firefox:
1. Download GeckoDriver from: https://github.com/mozilla/geckodriver/releases
2. Ensure GeckoDriver is in your PATH or specify the path in the script

### Python Dependencies
```bash
pip install selenium>=4.15.0
```

## Quick Start

### Basic Usage

```python
from scripts.selenium_template_antibot import AntiBotSeleniumTemplate

# Initialize the template (non-headless by default)
scraper = AntiBotSeleniumTemplate(browser="chrome", headless=False)

try:
    # Navigate to a website
    scraper.navigate_to_url("https://example.com")
    
    # Find and interact with elements
    search_box = scraper.find_element_by_id("search")
    if search_box:
        scraper.type_in_element(search_box, "search query")
    
    # Click buttons
    submit_btn = scraper.find_element_by_css_selector("button[type='submit']")
    if submit_btn:
        scraper.click_element(submit_btn)
    
    # Extract data
    results = scraper.find_elements_by_css_selector(".result-item")
    for result in results:
        print(result.text)

finally:
    # Always close the browser
    scraper.close_browser()
```

### Advanced Example

```python
# Initialize with Firefox in headless mode
scraper = AntiBotSeleniumTemplate(browser="firefox", headless=True)

try:
    # Navigate and wait for page load
    if scraper.navigate_to_url("https://forms.example.com"):
        
        # Fill out a form with various input types
        name_field = scraper.find_element_by_name("username")
        scraper.type_in_element(name_field, "John Doe")
        
        # Handle dropdown selection
        dropdown = scraper.find_element_by_id("country-select")
        scraper.select_dropdown_option(dropdown, option_text="United States")
        
        # Select radio button using XPath
        radio = scraper.find_element_by_xpath("//input[@name='gender' and @value='male']")
        scraper.click_element(radio)
        
        # Wait for specific element to be clickable
        submit_locator = ("css selector", "button.submit-btn")
        submit_btn = scraper.wait_for_element_to_be_clickable(submit_locator, timeout=15)
        
        if submit_btn:
            scraper.click_element(submit_btn)
            
        # Take screenshot for verification
        scraper.take_screenshot("form_submitted.png")

finally:
    scraper.close_browser()
```

## Configuration Options

### Browser Selection
- `browser="chrome"` (default) - Uses Chrome with anti-detection settings
- `browser="firefox"` - Uses Firefox with anti-detection settings

### Headless Mode
- `headless=False` (default) - Shows browser window (recommended for development)
- `headless=True` - Runs in background without GUI

### Timeouts and Delays
```python
# Custom delays for human-like behavior
scraper.human_delay(min_delay=1.0, max_delay=3.0)

# Custom timeouts for element finding
element = scraper.find_element_by_id("test", timeout=20)
```

## Anti-Bot Features Explained

### 1. User Agent Randomization
The template randomly selects from a pool of real browser user agents:
- Chrome on Windows 10/11
- Chrome on macOS
- Chrome on Linux

### 2. WebDriver Property Masking
JavaScript execution removes telltale signs of automation:
```javascript
Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})
```

### 3. Human-like Behavior
- Random delays between actions (1-3 seconds by default)
- Character-by-character typing with random keystroke delays
- Smooth scrolling with natural timing
- Mouse movement to elements before clicking

### 4. Browser Fingerprint Reduction
Chrome options that reduce detection:
- `--disable-blink-features=AutomationControlled`
- `--exclude-switches=enable-automation`
- `--disable-extensions`
- `--no-sandbox`

## Selector Methods Reference

| Method | Use Case | Example |
|--------|----------|---------|
| `find_element_by_id()` | Unique element IDs | `<div id="unique-id">` |
| `find_element_by_class_name()` | Single class name | `<div class="button">` |
| `find_element_by_css_selector()` | Complex CSS selectors | `div.container > p.text` |
| `find_element_by_xpath()` | Complex hierarchies | `//div[@class='item'][1]` |
| `find_element_by_name()` | Form inputs | `<input name="username">` |
| `find_element_by_tag_name()` | HTML tags | `<button>`, `<input>` |
| `find_element_by_link_text()` | Exact link text | `<a>Click Here</a>` |
| `find_element_by_partial_link_text()` | Partial link text | `<a>Click Here Now</a>` |

## Error Handling

The template includes comprehensive error handling:

```python
# All methods return None or False on failure, never crash
element = scraper.find_element_by_id("might-not-exist")
if element:
    success = scraper.click_element(element)
    if not success:
        print("Click failed, trying alternative method")
```

## Best Practices

### 1. Always Use Context Managers or Try/Finally
```python
scraper = AntiBotSeleniumTemplate()
try:
    # Your scraping code here
    pass
finally:
    scraper.close_browser()  # Always close
```

### 2. Check Return Values
```python
# Check if navigation succeeded
if scraper.navigate_to_url("https://example.com"):
    # Proceed with scraping
    pass
else:
    # Handle navigation failure
    pass
```

### 3. Use Appropriate Wait Times
```python
# For slow-loading elements, increase timeout
slow_element = scraper.find_element_by_id("slow", timeout=30)

# For dynamic content, wait for specific conditions
scraper.wait_for_text_in_element(("id", "status"), "Complete", timeout=60)
```

### 4. Take Screenshots for Debugging
```python
# Take screenshots at key points
scraper.take_screenshot("before_form_submission.png")
scraper.click_element(submit_button)
scraper.take_screenshot("after_form_submission.png")
```

## Troubleshooting

### Common Issues

#### 1. Element Not Found
- Increase timeout values
- Check if element is in an iframe
- Verify CSS selectors in browser DevTools
- Wait for page to fully load

#### 2. Click Intercepted
- The template automatically tries JavaScript click as fallback
- Ensure element is visible and not covered by other elements
- Try scrolling to element first

#### 3. Browser Driver Issues
- Ensure ChromeDriver/GeckoDriver is installed and in PATH
- Update driver to match browser version
- Check browser console for JavaScript errors

#### 4. Detection Still Occurring
- Increase delays between actions
- Vary user agents more frequently
- Consider using residential proxies
- Add more random behavior patterns

### Debug Mode
Enable detailed logging:
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)

scraper = AntiBotSeleniumTemplate()
# Now all actions will be logged in detail
```

## Performance Tips

1. **Use CSS Selectors**: Generally faster than XPath
2. **Minimize Screenshots**: Only take them when needed for debugging
3. **Adjust Delays**: Reduce delays for internal/testing sites
4. **Reuse Browser Instance**: Don't create new instances for each action
5. **Close Unused Tabs**: Use `driver.close()` for unused tabs

## Example Scripts

See `examples/selenium_template_example.py` for practical examples including:
- Search functionality
- Form interactions
- Data extraction with scrolling
- Multi-page navigation

## License

This template is part of the FDD Pipeline project and follows the same licensing terms. 