"""
MinerU Web API - Simplified Version
Easier to debug with synchronous code and minimal complexity
"""

import os
import time
import json
import requests
import shutil
import logging
from pathlib import Path
from functools import wraps
from playwright.sync_api import sync_playwright

# Configuration
LOGIN_URL = "https://mineru.net/OpenSourceTools/Extractor/PDF"
API_UPLOAD = "https://mineru.net/datasets/api/v2/file"
API_SUBMIT = "https://mineru.org.cn/api/v4/extract/task/batch"
API_TASKS = "https://mineru.net/api/v4/tasks"
API_DETAIL = "https://mineru.net/api/v4/extract/task/{task_id}"

AUTH_FILE = "mineru_auth.json"
DOWNLOAD_DIR = Path("mineru_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Configure logging
logger = logging.getLogger(__name__)

# Debug log file
debug_handler = logging.FileHandler("mineru_web_api_debug.log")
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
debug_handler.setFormatter(debug_formatter)
logger.addHandler(debug_handler)
logger.setLevel(logging.DEBUG)


def timing_decorator(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        logger.debug(f"Starting {func_name}")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.debug(f"Completed {func_name} in {elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"{func_name} failed after {elapsed:.2f}s: {e}")
            raise
    
    return wrapper


class MinerUAPI:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        logger.info("Initialized MinerUAPI")

    @timing_decorator
    def login(self, use_saved=True):
        """Simple login - either use saved auth or do browser login"""
        logger.info(f"Login called with use_saved={use_saved}")
        
        # Try saved auth first
        if use_saved:
            # Try main auth file, then error auth file
            auth_files = [AUTH_FILE, AUTH_FILE.replace(".json", "_error.json")]

            for auth_file in auth_files:
                if os.path.exists(auth_file):
                    try:
                        print(f"🔍 Trying saved auth from {auth_file}...")
                        logger.debug(f"Loading auth from {auth_file}")
                        
                        with open(auth_file, "r") as f:
                            auth_data = json.load(f)
                            cookies = auth_data.get("cookies", [])
                            logger.debug(f"Loaded {len(cookies)} cookies from auth file")

                            # Extract auth token
                            for cookie in cookies:
                                if cookie.get("name") == "uaa-token":
                                    self.auth_token = cookie.get("value")

                                    # Verify the auth still works
                                    print("🔍 Verifying saved authentication...")
                                    logger.debug(f"Found auth token: {self.auth_token[:10]}...")
                                    
                                    with sync_playwright() as p:
                                        browser = p.chromium.launch(headless=True)
                                        context = browser.new_context(
                                            storage_state=auth_file
                                        )
                                        page = context.new_page()
                                        
                                        logger.debug(f"Navigating to {LOGIN_URL} for verification")
                                        page.goto(LOGIN_URL)

                                        # Try multiple selectors
                                        selectors = [
                                            "button:has-text('URL Upload')",
                                            "button >> text=URL Upload",
                                            'button:has(img[alt=""]) >> text=URL Upload',
                                            "text=URL Upload",
                                        ]

                                        login_valid = False
                                        for selector in selectors:
                                            try:
                                                page.wait_for_selector(
                                                    selector, timeout=3000
                                                )
                                                login_valid = True
                                                break
                                            except:
                                                continue

                                        browser.close()

                                        if login_valid:
                                            print("✅ Saved authentication still valid")
                                            logger.info("Saved authentication verified successfully")
                                            self._setup_session(cookies)

                                            # If using error file, move it to main
                                            if auth_file != AUTH_FILE:
                                                shutil.move(auth_file, AUTH_FILE)
                                                print(
                                                    f"📁 Moved {auth_file} to {AUTH_FILE}"
                                                )

                                            return True
                                        else:
                                            print(
                                                "⚠️ Saved auth expired, need to login again"
                                            )
                                            logger.warning("Saved auth verification failed")

                    except Exception as e:
                        print(f"⚠️ Failed to use {auth_file}: {e}")
                        logger.error(f"Failed to load auth from {auth_file}: {e}", exc_info=True)

        # Browser login
        print("🌐 Opening browser for login...")
        logger.info("Starting browser-based login")
        
        with sync_playwright() as p:
            # Simple browser launch - no complex fallbacks
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Navigate and login
                page.goto(LOGIN_URL)

                # Check if login needed
                if "Login with GitHub" in page.content():
                    print("📝 Please login with GitHub...")
                    logger.debug("GitHub login required")
                    page.click("text=Login with GitHub")

                    # Wait for redirect back from GitHub
                    logger.debug("Waiting for GitHub redirect...")
                    page.wait_for_url("*mineru.net/*", timeout=60000)

                # Try multiple selectors for URL Upload button
                print("🔍 Checking login status...")
                login_confirmed = False

                selectors = [
                    "button:has-text('URL Upload')",
                    "button >> text=URL Upload",
                    'button:has(img[alt=""]) >> text=URL Upload',
                    "text=URL Upload",
                ]

                for selector in selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                        print(f"✅ Login confirmed with selector: {selector}")
                        logger.debug(f"Login verified with selector: {selector}")
                        login_confirmed = True
                        break
                    except:
                        logger.debug(f"Selector '{selector}' not found")
                        continue

                if not login_confirmed:
                    # Last attempt - check if we can see any upload-related elements
                    try:
                        page.wait_for_selector("text=Upload", timeout=5000)
                        login_confirmed = True
                        print("✅ Login confirmed (found Upload text)")
                    except:
                        raise Exception("Could not confirm login status")

                print("✅ Login successful!")
                logger.info("Browser login successful")

                # Get cookies
                cookies = context.cookies()
                logger.debug(f"Retrieved {len(cookies)} cookies from browser")

                # Save auth for next time
                storage_state = context.storage_state()
                with open(AUTH_FILE, "w") as f:
                    json.dump(storage_state, f)
                print(f"💾 Saved authentication to {AUTH_FILE}")
                logger.info(f"Saved authentication to {AUTH_FILE}")

                # Extract auth token
                for cookie in cookies:
                    if cookie.get("name") == "uaa-token":
                        self.auth_token = cookie.get("value")
                        logger.debug(f"Extracted auth token: {self.auth_token[:10]}...")
                        break

                if not self.auth_token:
                    logger.error("No auth token found in cookies")
                    raise Exception("Failed to get auth token from cookies")

                self._setup_session(cookies)
                return True

            except Exception as e:
                # Always try to save cookies on error in case we were logged in
                print(f"⚠️ Error occurred: {e}")
                print("💾 Attempting to save cookies anyway...")
                logger.error(f"Login error: {e}", exc_info=True)

                try:
                    cookies = context.cookies()
                    storage_state = context.storage_state()

                    # Save with error suffix to distinguish
                    error_auth_file = AUTH_FILE.replace(".json", "_error.json")
                    with open(error_auth_file, "w") as f:
                        json.dump(storage_state, f)
                    print(f"💾 Saved error state to {error_auth_file}")

                    # Check if we got auth token
                    for cookie in cookies:
                        if cookie.get("name") == "uaa-token":
                            self.auth_token = cookie.get("value")
                            print("✅ Found auth token in cookies despite error!")
                            logger.info("Recovered auth token from error state")
                            self._setup_session(cookies)

                            # Move error file to main auth file since it has valid token
                            shutil.move(error_auth_file, AUTH_FILE)
                            logger.info(f"Moved {error_auth_file} to {AUTH_FILE}")
                            return True
                except Exception as save_error:
                    print(f"❌ Could not save error state: {save_error}")
                    logger.error(f"Failed to save error state: {save_error}")

                raise e
            finally:
                browser.close()

    def _setup_session(self, cookies):
        """Setup requests session with auth headers"""
        logger.debug("Setting up session with auth headers")
        
        # Build cookie string
        cookie_parts = []
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if (
                name in ["uaa-token", "opendatalab_session", "ssouid", "acw_tc"]
                and value
            ):
                cookie_parts.append(f"{name}={value}")
                logger.debug(f"Added cookie: {name}")

        # Set headers
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Cookie": "; ".join(cookie_parts),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://mineru.net/OpenSourceTools/Extractor",
        }
        
        self.session.headers.update(headers)
        logger.info(f"Session configured with {len(cookie_parts)} cookies")

    @timing_decorator
    def process_pdf(self, pdf_url, wait_time=300):
        """Process a PDF URL through MinerU"""
        if not self.auth_token:
            logger.error("Not authenticated")
            raise Exception("Not logged in. Call login() first.")

        print(f"\n📄 Processing: {pdf_url}")
        filename = os.path.basename(pdf_url) or "document.pdf"
        
        logger.info(f"Starting PDF processing: {pdf_url}")

        # Step 1: Submit for processing
        print("1️⃣ Submitting PDF...")
        logger.debug(f"Submitting PDF: {pdf_url}")
        task_id = self._submit_pdf(pdf_url, filename)
        if not task_id:
            logger.error("Failed to submit PDF")
            raise Exception("Failed to submit PDF")

        print(f"   Task ID: {task_id}")
        logger.info(f"PDF submitted successfully, task_id: {task_id}")

        # Step 2: Wait for completion
        print("2️⃣ Waiting for processing...")
        logger.debug(f"Waiting for task {task_id} completion")
        if not self._wait_for_completion(task_id, wait_time):
            logger.error(f"Task {task_id} processing failed")
            raise Exception("Processing timed out or failed")

        # Step 3: Get results
        print("3️⃣ Getting results...")
        logger.debug(f"Getting results for task {task_id}")
        results = self._get_results(task_id)
        logger.info(f"Retrieved results for task {task_id}")

        # Step 4: Download files
        print("4️⃣ Downloading files...")
        logger.debug("Downloading result files")
        self._download_files(results, filename)

        print("✅ Complete!")
        logger.info(f"PDF processing completed for task {task_id}")
        return results

    @timing_decorator
    def _submit_pdf(self, pdf_url, filename):
        """Submit PDF for processing"""
        import uuid
        
        logger.debug(f"Submitting PDF: url={pdf_url}, filename={filename}")

        payload = {
            "is_ocr": False,
            "enable_formula": True,
            "enable_table": True,
            "model_version": "v2",
            "language": None,
            "files": [
                {"url": pdf_url, "data_id": str(uuid.uuid4()), "file_name": filename}
            ],
        }

        logger.debug(f"Sending POST to {API_SUBMIT}")
        response = self.session.post(API_SUBMIT, json=payload)
        data = response.json()
        
        logger.debug(f"Submit response: status={response.status_code}, data={data}")

        if data.get("code") == 0:
            task_ids = data.get("data", {}).get("task_ids", [])
            task_id = task_ids[0] if task_ids else None
            logger.info(f"PDF submitted, task_id: {task_id}")
            return task_id

        print(f"❌ Submit failed: {data}")
        logger.error(f"Submit failed: {data}")
        return None

    @timing_decorator
    def _wait_for_completion(self, task_id, max_wait=300):
        """Poll for task completion"""
        start = time.time()
        logger.debug(f"Polling task {task_id}, max_wait={max_wait}s")

        while time.time() - start < max_wait:
            # Get task list
            response = self.session.get(f"{API_TASKS}?page_no=1&page_size=20&type=")
            data = response.json()

            # Find our task
            tasks = data.get("data", {}).get("list", [])
            task = next((t for t in tasks if t["task_id"] == task_id), None)

            if task:
                state = task.get("state", "").lower()
                print(f"   Status: {state}")
                logger.debug(f"Task {task_id} status: {state}, elapsed: {time.time() - start:.1f}s")

                if state == "done":
                    logger.info(f"Task {task_id} completed successfully")
                    return True
                elif state == "error":
                    error_msg = task.get('err_msg', 'Unknown')
                    print(f"❌ Error: {error_msg}")
                    logger.error(f"Task {task_id} failed: {error_msg}")
                    return False

            time.sleep(10)

        logger.warning(f"Task {task_id} timed out after {max_wait}s")
        return False

    @timing_decorator
    def _get_results(self, task_id):
        """Get download URLs for results"""
        url = API_DETAIL.format(task_id=task_id)
        logger.debug(f"Getting results from {url}")
        
        response = self.session.get(url)
        data = response.json().get("data", {})
        
        logger.debug(f"Results response: {data}")

        results = {
            "markdown": data.get("full_md_link"),
            "json": data.get("layout_url"),
            "filename": data.get("file_name", "output"),
        }
        
        logger.info(
            f"Retrieved results - has_markdown: {bool(results['markdown'])}, "
            f"has_json: {bool(results['json'])}"
        )
        
        return results

    @timing_decorator
    def _download_files(self, results, filename):
        """Download result files"""
        base_name = os.path.splitext(filename)[0]
        logger.debug(f"Downloading files for {filename}")

        # Download markdown
        if results.get("markdown"):
            self._download(results["markdown"], f"{base_name}.md")

        # Download JSON
        if results.get("json"):
            self._download(results["json"], f"{base_name}.json")

    @timing_decorator
    def _download(self, url, filename):
        """Download a single file"""
        filepath = DOWNLOAD_DIR / filename
        print(f"   ⬇️  Downloading to: {filepath}")
        logger.debug(f"Downloading {url} to {filepath}")
        
        response = self.session.get(url, stream=True)
        total_size = 0

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)

        print(f"   ✓ Downloaded: {filename}")
        logger.info(f"Downloaded {filename} ({total_size:,} bytes)")


# Simple usage example
if __name__ == "__main__":
    import sys
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create API instance
    api = MinerUAPI()

    # Clean up old error auth files
    error_auth = AUTH_FILE.replace(".json", "_error.json")
    if os.path.exists(error_auth):
        print(f"🧹 Cleaning up old error auth file: {error_auth}")
        logger.info(f"Removing old error auth file: {error_auth}")
        os.remove(error_auth)

    # Login
    api.login(use_saved=True)

    # Process PDF
    if len(sys.argv) > 1:
        pdf_url = sys.argv[1]
    else:
        pdf_url = "https://smologfkmyahtgbzhkqu.supabase.co/storage/v1/object/public/fdds//480234_New%20York_Initial_10-15-2024.pdf"

    print("\n" + "="*60)
    print("MinerU Web API Demo")
    print("="*60 + "\n")
    
    print("Configuration:")
    print(f"  Login URL: {LOGIN_URL}")
    print(f"  Submit API: {API_SUBMIT}")
    print(f"  Auth File: {AUTH_FILE}")
    print(f"  Downloads: {DOWNLOAD_DIR}")
    print("\n" + "="*60 + "\n")
    
    try:
        results = api.process_pdf(pdf_url)
        print(f"\n📁 Files saved to: {DOWNLOAD_DIR}")
        
        print("\nProcessing Summary:")
        print(f"  Task completed successfully")
        print(f"  Markdown: {'✅' if results.get('markdown') else '❌'}")
        print(f"  JSON: {'✅' if results.get('json') else '❌'}")
        print(f"  Filename: {results.get('filename')}")
        
        # List downloaded files
        print("\nDownloaded files:")
        for file in DOWNLOAD_DIR.iterdir():
            print(f"  - {file.name} ({file.stat().st_size:,} bytes)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Processing failed: {e}", exc_info=True)
    
    print("\n" + "="*60)
    print("Demo completed! Check mineru_web_api_debug.log for details.")
    print("="*60)
