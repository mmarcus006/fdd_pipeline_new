# hybrid_mineru_bot.py

import asyncio
import os
import time
import uuid
import requests
from playwright.async_api import async_playwright, expect

# --- Configuration Constants ---
LOGIN_URL = "https://mineru.net/OpenSourceTools/Extractor/PDF"
PDF_URL_TO_PROCESS = "https://smologfkmyahtgbzhkqu.supabase.co/storage/v1/object/public/fdds//480234_New%20York_Initial_10-15-2024.pdf"
AUTH_FILE = "auth.json"
DOWNLOAD_PATH = "hybrid_downloads"

# API Endpoints
API_BASE_URL_ORG = "https://mineru.org.cn/api/v4"
API_BASE_URL_NET = "https://mineru.net/api/v4"
SUBMIT_URL = f"{API_BASE_URL_ORG}/extract/task/batch"
TASKS_URL = f"{API_BASE_URL_NET}/tasks"
RESULT_URL_TEMPLATE = f"{API_BASE_URL_NET}/extract/task/{{task_id}}"
CONVERT_URL_TEMPLATE = f"{API_BASE_URL_ORG}/task/{{task_id}}/convert"


async def login_and_extract_token() -> str:
    """
    Uses Playwright to automate the browser login process via GitHub
    and extracts the necessary authentication token from the cookies.
    
    Returns:
        str: The 'uaa-token' needed for subsequent API calls.
    
    Raises:
        FileNotFoundError: If the authentication state file is missing.
        Exception: If login fails or the token cannot be found.
    """
    print("--- Step 1: Automating Login with Playwright ---")
    if not os.path.exists(AUTH_FILE):
        raise FileNotFoundError(
            f"Error: '{AUTH_FILE}' not found. "
            "Please run the 'save_auth_state.py' script first to log in manually."
        )

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True) # Can be set to False for debugging
        context = await browser.new_context(storage_state=AUTH_FILE)
        page = await context.new_page()

        try:
            print("Navigating to MinerU and initiating login...")
            await page.goto(LOGIN_URL)

            # Attempt to click the GitHub login button. If it's not there,
            # the site may have auto-logged us in based on cookies.
            try:
                await page.get_by_text("Login with GitHub").click(timeout=10000)
            except Exception:
                print("Login button not found, proceeding as if already logged in.")

            # A reliable way to confirm login is checking for an element
            # that only appears when authenticated.
            await expect(page.get_by_text("My Account")).to_be_visible(timeout=45000)
            print("Login successful!")

            print("Extracting authentication token from browser session...")
            cookies = await context.cookies()
            uaa_token = next(
                (cookie['value'] for cookie in cookies if cookie['name'] == 'uaa-token'),
                None
            )

            if not uaa_token:
                raise Exception("Failed to find 'uaa-token' in cookies after login.")
            
            print("Token extracted successfully.")
            return uaa_token

        finally:
            await browser.close()


def run_api_workflow(token: str):
    """
    Uses the requests library and the extracted token to perform the
    PDF submission, status polling, and file downloading.
    
    Args:
        token (str): The authentication token obtained from the browser session.
    """
    print("\n--- Step 2: Executing API Workflow with Requests ---")
    
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Origin": "https://mineru.net",
        "Referer": "https://mineru.net/",
    })

    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)

    try:
        # 1. Submit PDF for conversion
        print("Submitting PDF for processing...")
        submit_payload = {
            "files": [{"url": PDF_URL_TO_PROCESS, "data_id": str(uuid.uuid4())}],
            "is_ocr": False, "enable_formula": True, "enable_table": True,
            "model_version": "v2", "language": None
        }
        submit_res = session.post(SUBMIT_URL, json=submit_payload)
        submit_res.raise_for_status()
        task_id = submit_res.json()["data"]["task_ids"][0]
        print(f"Task created with ID: {task_id}")

        # 2. Poll for task completion
        print("Polling for task status (this may take a few minutes)...")
        timeout, poll_interval = 240, 10
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_res = session.get(TASKS_URL)
            status_res.raise_for_status()
            task_list = status_res.json()["data"]["list"]
            current_task = next((t for t in task_list if t["task_id"] == task_id), None)

            if not current_task:
                print(f"Waiting for task {task_id} to appear in list...")
            else:
                state = current_task['state']
                print(f"  Current status: {state.upper()}")
                if state == "done":
                    print("  Task finished successfully!")
                    break
                elif state == "error":
                    raise Exception(f"Task failed: {current_task.get('err_msg')}")
            
            time.sleep(poll_interval)
        else:
            raise Exception("Polling timed out.")

        # 3. Download results
        print("Fetching final result links and downloading files...")
        result_res = session.get(RESULT_URL_TEMPLATE.format(task_id=task_id))
        result_res.raise_for_status()
        result_data = result_res.json()["data"]
        file_name_base = os.path.splitext(result_data["file_name"])[0]

        # Download Markdown and JSON
        download_file(session, result_data["full_md_link"], f"{file_name_base}.md")
        download_file(session, result_data["layout_url"], f"{file_name_base}.json")

        # 4. Convert to other formats and download
        for file_format in ["html", "docx"]:
            print(f"Requesting conversion to '{file_format}'...")
            convert_res = session.post(
                CONVERT_URL_TEMPLATE.format(task_id=task_id),
                json={"to": file_format}
            )
            convert_res.raise_for_status()
            download_url = convert_res.json()["data"]
            download_filename = os.path.basename(download_url)
            download_file(session, download_url, download_filename)

    except requests.exceptions.RequestException as e:
        print(f"An API error occurred: {e}")
        if e.response:
            print(f"Response Body: {e.response.text}")


def download_file(session: requests.Session, url: str, filename: str):
    """Downloads a file from a URL using the provided session."""
    filepath = os.path.join(DOWNLOAD_PATH, filename)
    try:
        with session.get(url, stream=True) as r:
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"  Successfully downloaded '{filename}'")
    except requests.exceptions.RequestException as e:
        print(f"  Failed to download '{filename}'. Error: {e}")


async def main():
    """Main function to orchestrate the login and API workflow."""
    try:
        auth_token = await login_and_extract_token()
        run_api_workflow(auth_token)
        print(f"\n✅ Workflow complete. Files are in the '{DOWNLOAD_PATH}' directory.")
    except Exception as e:
        print(f"\n❌ An error occurred during the process: {e}")


if __name__ == "__main__":
    asyncio.run(main())