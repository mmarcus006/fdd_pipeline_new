"""
Alternative MinerU Web API Integration using existing Firefox session
This version connects to your running Firefox browser
"""

import asyncio
import os
import time
import uuid
import requests
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Union
from urllib.parse import quote, urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration Constants ---
LOGIN_URL = "https://mineru.net/OpenSourceTools/Extractor/PDF"

# API Endpoints
API_V2_FILE_UPLOAD = "https://mineru.net/datasets/api/v2/file"
API_V4_BATCH_SUBMIT = "https://mineru.org.cn/api/v4/extract/task/batch"
API_V4_TASKS_LIST = "https://mineru.net/api/v4/tasks"
API_V4_TASK_DETAIL = "https://mineru.net/api/v4/extract/task/{task_id}"

# File paths
DOWNLOAD_PATH = "mineru_downloads"

# Timeouts and intervals
POLL_INTERVAL = 10  # seconds
MAX_POLL_TIME = 300  # 5 minutes


class MinerUWebAPIAlternative:
    """Alternative approach using manual cookie extraction"""
    
    def __init__(self, download_path: str = DOWNLOAD_PATH):
        self.download_path = Path(download_path)
        self.download_path.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.auth_token = None
        self.cookies = {}
    
    def extract_cookies_manually(self):
        """
        Manual process to extract cookies from browser
        """
        print("\n" + "="*80)
        print("MANUAL COOKIE EXTRACTION PROCESS")
        print("="*80)
        print("1. Open Firefox and navigate to: https://mineru.net")
        print("2. Make sure you are logged in via GitHub")
        print("3. Open Developer Tools (F12)")
        print("4. Go to the 'Storage' or 'Application' tab")
        print("5. Find the following cookies and paste their values below:")
        print("="*80 + "\n")
        
        # Get cookie values from user
        self.auth_token = input("Enter 'uaa-token' value: ").strip()
        self.cookies['uaa-token'] = self.auth_token
        self.cookies['opendatalab_session'] = input("Enter 'opendatalab_session' value (or press Enter to use same as uaa-token): ").strip() or self.auth_token
        self.cookies['ssouid'] = input("Enter 'ssouid' value: ").strip()
        
        # Optional cookie
        acw_tc = input("Enter 'acw_tc' value (optional, press Enter to skip): ").strip()
        if acw_tc:
            self.cookies['acw_tc'] = acw_tc
        
        logger.info(f"Extracted {len(self.cookies)} cookies")
        
        # Save cookies for future use
        self._save_cookies()
        
        return True
    
    def _save_cookies(self):
        """Save cookies to a file for reuse"""
        import json
        cookie_file = Path("mineru_cookies.json")
        with open(cookie_file, 'w') as f:
            json.dump(self.cookies, f, indent=2)
        logger.info(f"Cookies saved to {cookie_file}")
    
    def _load_cookies(self) -> bool:
        """Load cookies from file if available"""
        import json
        cookie_file = Path("mineru_cookies.json")
        if cookie_file.exists():
            try:
                with open(cookie_file, 'r') as f:
                    self.cookies = json.load(f)
                self.auth_token = self.cookies.get('uaa-token')
                logger.info("Loaded saved cookies")
                return True
            except:
                pass
        return False
    
    def _prepare_session(self):
        """Prepare requests session with headers and cookies"""
        self.session.headers.update({
            "Authorization": f"Bearer {self.auth_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "DNT": "1",
            "Origin": "https://mineru.net",
            "Referer": "https://mineru.net/OpenSourceTools/Extractor",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        })
        
        # Set cookies
        for name, value in self.cookies.items():
            self.session.cookies.set(name, value, domain=".mineru.net")
    
    async def process_pdf(self, pdf_input: Union[str, bytes, Path], filename: Optional[str] = None) -> Dict[str, str]:
        """
        Process a PDF through the complete MinerU workflow
        
        Args:
            pdf_input: URL string, file path, or bytes content of PDF
            filename: Optional filename (required if pdf_input is bytes)
            
        Returns:
            Dict containing download URLs for processed files
        """
        if not self.auth_token:
            # Try to load saved cookies first
            if not self._load_cookies():
                # If no saved cookies, do manual extraction
                self.extract_cookies_manually()
        
        self._prepare_session()
        
        # Determine input type and get URL
        if isinstance(pdf_input, bytes):
            # Binary data provided
            if not filename:
                filename = "document.pdf"
            logger.info(f"Processing PDF from binary data: {filename}")
            pdf_url = await self._upload_file_bytes(pdf_input, filename)
        elif isinstance(pdf_input, (str, Path)):
            pdf_str = str(pdf_input)
            if pdf_str.startswith(('http://', 'https://')):
                # URL provided
                pdf_url = pdf_str
                filename = filename or os.path.basename(urlparse(pdf_url).path) or "document.pdf"
                logger.info(f"Processing PDF from URL: {filename}")
            else:
                # Local file path provided
                file_path = Path(pdf_str)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")
                filename = filename or file_path.name
                logger.info(f"Processing PDF from file: {filename}")
                with open(file_path, 'rb') as f:
                    pdf_url = await self._upload_file_bytes(f.read(), filename)
        else:
            raise TypeError("pdf_input must be a URL string, file path, or bytes")
        
        # Step 2: Submit for processing (API v4)
        task_id = await self._submit_for_processing(pdf_url, filename)
        if not task_id:
            raise Exception("Failed to submit file for processing")
        
        logger.info(f"Task created with ID: {task_id}")
        
        # Step 3: Poll for completion
        task_data = await self._poll_task_status(task_id)
        if not task_data:
            raise Exception("Task processing failed or timed out")
        
        # Step 4: Get download URLs
        result_urls = await self._get_result_urls(task_id)
        
        # Download files
        await self._download_results(result_urls, filename)
        
        return result_urls
    
    # Copy all the other methods from the main script (_upload_file_bytes, _submit_for_processing, etc.)
    # For brevity, I'm not including them here, but they would be identical to the main script
    
    async def _upload_file_bytes(self, file_bytes: bytes, filename: str) -> str:
        """Upload binary file data to MinerU and return the URL"""
        logger.info(f"Uploading file: {filename} ({len(file_bytes)} bytes)")
        
        # First, register the file to get upload URL
        upload_info = await self._register_file_for_upload(filename)
        if not upload_info:
            raise Exception("Failed to get upload URL")
        
        upload_url = upload_info.get("uploadUrl")
        final_url = upload_info.get("url")
        
        if not upload_url or not final_url:
            raise Exception("Invalid upload response from server")
        
        # Upload the file
        headers = {
            "Content-Type": "application/pdf",
            "Content-Length": str(len(file_bytes))
        }
        
        try:
            response = requests.put(upload_url, data=file_bytes, headers=headers)
            response.raise_for_status()
            logger.info(f"File uploaded successfully to: {final_url}")
            return final_url
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise
    
    async def _register_file_for_upload(self, filename: str) -> Optional[Dict]:
        """Register file with API v2 to get upload URL"""
        logger.info("Getting upload URL from API v2...")
        
        url = f"{API_V2_FILE_UPLOAD}?fileName={quote(filename)}&openRead=true&fileType=mineru"
        
        headers = self.session.headers.copy()
        headers.update({
            "Content-Length": "0",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        })
        
        try:
            response = self.session.post(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") == 200:
                upload_info = data.get("data", {})
                logger.info(f"Got upload URL for file: {filename}")
                return upload_info
            else:
                logger.error(f"Failed to get upload URL: {data}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting upload URL: {e}")
            return None
    
    async def _submit_for_processing(self, file_url: str, filename: str) -> Optional[str]:
        """Submit file for processing via API v4"""
        logger.info("Submitting file for processing...")
        
        headers = self.session.headers.copy()
        headers.update({
            "accept": "application/json",
            "content-type": "application/json",
            "Referer": "https://mineru.net/",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Storage-Access": "active"
        })
        
        payload = {
            "is_ocr": False,
            "enable_formula": True,
            "enable_table": True,
            "model_version": "v2",
            "language": None,
            "files": [{
                "url": file_url,
                "data_id": str(uuid.uuid4()),
                "file_name": filename
            }]
        }
        
        try:
            response = self.session.post(API_V4_BATCH_SUBMIT, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") == 0:
                task_ids = data.get("data", {}).get("task_ids", [])
                if task_ids:
                    return task_ids[0]
            
            logger.error(f"Submission failed: {data}")
            return None
            
        except Exception as e:
            logger.error(f"Error submitting for processing: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            return None
    
    async def _poll_task_status(self, task_id: str) -> Optional[Dict]:
        """Poll for task completion"""
        logger.info("Polling for task completion...")
        
        start_time = time.time()
        
        while time.time() - start_time < MAX_POLL_TIME:
            try:
                response = self.session.get(f"{API_V4_TASKS_LIST}?page_no=1&page_size=20&type=")
                response.raise_for_status()
                
                data = response.json()
                task_list = data.get("data", {}).get("list", [])
                
                current_task = next((t for t in task_list if t["task_id"] == task_id), None)
                
                if current_task:
                    state = current_task.get("state", "").lower()
                    logger.info(f"Task status: {state.upper()}")
                    
                    if state == "done":
                        logger.info("Task completed successfully!")
                        return current_task
                    elif state == "error":
                        logger.error(f"Task failed: {current_task.get('err_msg', 'Unknown error')}")
                        return None
                else:
                    logger.info(f"Task {task_id} not found in list yet...")
                
            except Exception as e:
                logger.error(f"Error polling task status: {e}")
            
            await asyncio.sleep(POLL_INTERVAL)
        
        logger.error("Task polling timed out")
        return None
    
    async def _get_result_urls(self, task_id: str) -> Dict[str, str]:
        """Get download URLs for processed files"""
        logger.info("Getting result URLs...")
        
        try:
            response = self.session.get(API_V4_TASK_DETAIL.format(task_id=task_id))
            response.raise_for_status()
            
            data = response.json()
            result_data = data.get("data", {})
            
            urls = {
                "markdown": result_data.get("full_md_link"),
                "json": result_data.get("layout_url"),
                "filename": result_data.get("file_name", "output")
            }
            
            logger.info(f"Retrieved download URLs for: {urls['filename']}")
            return urls
            
        except Exception as e:
            logger.error(f"Error getting result URLs: {e}")
            return {}
    
    async def _download_results(self, urls: Dict[str, str], base_filename: str):
        """Download the processed files"""
        logger.info("Downloading processed files...")
        
        base_name = os.path.splitext(base_filename)[0]
        
        if urls.get("markdown"):
            await self._download_file(urls["markdown"], f"{base_name}.md")
        
        if urls.get("json"):
            await self._download_file(urls["json"], f"{base_name}.json")
        
        logger.info(f"Downloads complete. Files saved to: {self.download_path}")
    
    async def _download_file(self, url: str, filename: str):
        """Download a single file"""
        filepath = self.download_path / filename
        
        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Downloaded: {filename}")
            
        except Exception as e:
            logger.error(f"Failed to download {filename}: {e}")


async def main():
    """Example usage"""
    import sys
    
    api = MinerUWebAPIAlternative()
    
    try:
        if len(sys.argv) > 1:
            pdf_input = sys.argv[1]
            logger.info(f"Processing: {pdf_input}")
            results = await api.process_pdf(pdf_input)
        else:
            # Demo URL
            demo_url = "https://smologfkmyahtgbzhkqu.supabase.co/storage/v1/object/public/fdds//480234_New%20York_Initial_10-15-2024.pdf"
            logger.info(f"Running demo with URL: {demo_url}")
            results = await api.process_pdf(demo_url)
        
        logger.info("✅ Processing complete!")
        logger.info(f"Results: {results}")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())