"""
MinerU Web API Integration for FDD Pipeline
Handles PDF processing through MinerU's web service with UUID tracking and Google Drive storage
"""

import os
import time
import json
import requests
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from uuid import UUID
from datetime import datetime
import asyncio

from playwright.sync_api import sync_playwright
from prefect import task

from config import get_settings
from utils.logging import PipelineLogger
from storage.google_drive import get_drive_manager
from models.section import FDDSection


class MinerUProcessor:
    """MinerU Web API client with FDD Pipeline integration."""

    def __init__(self):
        self.settings = get_settings()
        self.logger = PipelineLogger("mineru_processor")
        self.session = requests.Session()
        self.auth_token = None
        self.drive_manager = get_drive_manager()

        # Configuration
        self.login_url = "https://mineru.net/OpenSourceTools/Extractor/PDF"
        self.api_submit = "https://mineru.org.cn/api/v4/extract/task/batch"
        self.api_tasks = "https://mineru.net/api/v4/tasks"
        self.api_detail = "https://mineru.net/api/v4/extract/task/{task_id}"

        # Auth file in project root
        self.auth_file = Path(self.settings.project_root) / "mineru_auth.json"

    def login(self, use_saved: bool = True) -> bool:
        """Authenticate with MinerU using saved auth or browser login."""
        # Try saved auth first
        if use_saved and self.auth_file.exists():
            try:
                self.logger.info("Attempting to use saved authentication")
                with open(self.auth_file, "r") as f:
                    auth_data = json.load(f)
                    cookies = auth_data.get("cookies", [])

                    # Extract auth token
                    for cookie in cookies:
                        if cookie["name"] == "uaa-token":
                            self.auth_token = cookie["value"]

                            # Verify auth still works
                            if self._verify_auth(auth_data):
                                self._setup_session(cookies)
                                self.logger.info(
                                    "Successfully loaded saved authentication"
                                )
                                return True
                            else:
                                self.logger.warning(
                                    "Saved auth expired, need to login again"
                                )

            except Exception as e:
                self.logger.warning(f"Failed to use saved auth: {e}")

        # Browser login
        return self._browser_login()

    def _verify_auth(self, auth_data: Dict) -> bool:
        """Verify saved authentication is still valid."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=auth_data)
                page = context.new_page()
                page.goto(self.login_url)

                # Check for upload button
                try:
                    page.wait_for_selector(
                        "button:has-text('URL Upload')", timeout=3000
                    )
                    browser.close()
                    return True
                except:
                    browser.close()
                    return False

        except Exception as e:
            self.logger.error(f"Auth verification failed: {e}")
            return False

    def _browser_login(self) -> bool:
        """Perform browser-based login."""
        self.logger.info("Opening browser for MinerU login")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Navigate to login page
                page.goto(self.login_url)

                # Check if login needed
                if "Login with GitHub" in page.content():
                    self.logger.info("Please login with GitHub")
                    page.click("text=Login with GitHub")

                    # Wait for redirect back from GitHub
                    page.wait_for_url("*mineru.net/*", timeout=60000)

                # Verify login success
                page.wait_for_selector("button:has-text('URL Upload')", timeout=5000)
                self.logger.info("Login successful!")

                # Get cookies and save auth
                cookies = context.cookies()
                storage_state = context.storage_state()

                with open(self.auth_file, "w") as f:
                    json.dump(storage_state, f)

                self.logger.info(f"Saved authentication to {self.auth_file}")

                # Extract auth token
                for cookie in cookies:
                    if cookie["name"] == "uaa-token":
                        self.auth_token = cookie["value"]
                        break

                if not self.auth_token:
                    raise Exception("Failed to get auth token from cookies")

                self._setup_session(cookies)
                return True

            except Exception as e:
                self.logger.error(f"Browser login failed: {e}")
                raise
            finally:
                browser.close()

    def _setup_session(self, cookies: list):
        """Setup requests session with auth headers."""
        cookie_parts = []
        for cookie in cookies:
            if cookie["name"] in [
                "uaa-token",
                "opendatalab_session",
                "ssouid",
                "acw_tc",
            ]:
                cookie_parts.append(f"{cookie['name']}={cookie['value']}")

        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.auth_token}",
                "Cookie": "; ".join(cookie_parts),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://mineru.net/OpenSourceTools/Extractor",
            }
        )

    async def process_pdf_with_storage(
        self, pdf_url: str, fdd_uuid: UUID, franchise_name: str, wait_time: int = 300
    ) -> Dict[str, Any]:
        """
        Process PDF through MinerU and store results in Google Drive.

        Args:
            pdf_url: URL of the PDF to process
            fdd_uuid: UUID of the FDD record
            franchise_name: Name of the franchise for folder organization
            wait_time: Maximum time to wait for processing

        Returns:
            Dictionary with processing results and Google Drive file IDs
        """
        if not self.auth_token:
            raise Exception("Not authenticated. Call login() first.")

        self.logger.info(
            "Processing PDF with MinerU",
            pdf_url=pdf_url,
            fdd_uuid=str(fdd_uuid),
            franchise_name=franchise_name,
        )

        # Submit for processing
        task_id = await self._submit_pdf(pdf_url, franchise_name)
        if not task_id:
            raise Exception("Failed to submit PDF to MinerU")

        self.logger.info(f"MinerU task created: {task_id}")

        # Wait for completion
        if not await self._wait_for_completion(task_id, wait_time):
            raise Exception("MinerU processing timed out or failed")

        # Get results
        results = await self._get_results(task_id)

        # Download and store in Google Drive
        drive_results = await self._store_results_in_drive(
            results, fdd_uuid, franchise_name
        )

        return {
            "task_id": task_id,
            "mineru_results": results,
            "drive_files": drive_results,
            "fdd_uuid": str(fdd_uuid),
            "processed_at": datetime.utcnow().isoformat(),
        }

    async def _submit_pdf(self, pdf_url: str, filename: str) -> Optional[str]:
        """Submit PDF for processing."""
        import uuid

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

        response = await asyncio.to_thread(
            self.session.post, self.api_submit, json=payload
        )
        data = response.json()

        if data.get("code") == 0:
            task_ids = data.get("data", {}).get("task_ids", [])
            return task_ids[0] if task_ids else None

        self.logger.error(f"Submit failed: {data}")
        return None

    async def _wait_for_completion(self, task_id: str, max_wait: int = 300) -> bool:
        """Poll for task completion."""
        start = time.time()

        while time.time() - start < max_wait:
            # Get task list
            response = await asyncio.to_thread(
                self.session.get, f"{self.api_tasks}?page_no=1&page_size=20&type="
            )
            data = response.json()

            # Find our task
            tasks = data.get("data", {}).get("list", [])
            task = next((t for t in tasks if t["task_id"] == task_id), None)

            if task:
                state = task.get("state", "").lower()
                self.logger.debug(f"MinerU task status: {state}")

                if state == "done":
                    return True
                elif state == "error":
                    self.logger.error(f"MinerU error: {task.get('err_msg', 'Unknown')}")
                    return False

            await asyncio.sleep(10)

        return False

    async def _get_results(self, task_id: str) -> Dict[str, Any]:
        """Get download URLs for results."""
        response = await asyncio.to_thread(
            self.session.get, self.api_detail.format(task_id=task_id)
        )
        data = response.json().get("data", {})

        return {
            "markdown_url": data.get("full_md_link"),
            "json_url": data.get("layout_url"),
            "filename": data.get("file_name", "output"),
        }

    async def _store_results_in_drive(
        self, results: Dict[str, Any], fdd_uuid: UUID, franchise_name: str
    ) -> Dict[str, str]:
        """Download MinerU results and store in Google Drive."""
        drive_files = {}

        # Create UUID-based folder structure
        # Target folder: {root_folder}/{fdd_uuid}/
        folder_path = str(fdd_uuid)

        try:
            # Download markdown
            if results.get("markdown_url"):
                md_content = await self._download_file(results["markdown_url"])

                # Upload to Google Drive
                file_id, metadata = await asyncio.to_thread(
                    self.drive_manager.upload_file_with_metadata_sync,
                    md_content,
                    f"{franchise_name}_mineru.md",
                    folder_path,
                    fdd_uuid,
                    "mineru_markdown",
                    "text/markdown",
                )

                drive_files["markdown"] = {
                    "file_id": file_id,
                    "drive_path": metadata.drive_path,
                    "size": len(md_content),
                }

                self.logger.info(
                    "Uploaded MinerU markdown to Google Drive",
                    file_id=file_id,
                    path=metadata.drive_path,
                )

            # Download JSON layout
            if results.get("json_url"):
                json_content = await self._download_file(results["json_url"])

                # Upload to Google Drive
                file_id, metadata = await asyncio.to_thread(
                    self.drive_manager.upload_file_with_metadata_sync,
                    json_content,
                    f"{franchise_name}_layout.json",
                    folder_path,
                    fdd_uuid,
                    "mineru_layout",
                    "application/json",
                )

                drive_files["json"] = {
                    "file_id": file_id,
                    "drive_path": metadata.drive_path,
                    "size": len(json_content),
                }

                self.logger.info(
                    "Uploaded MinerU JSON to Google Drive",
                    file_id=file_id,
                    path=metadata.drive_path,
                )

            return drive_files

        except Exception as e:
            self.logger.error(f"Failed to store results in Google Drive: {e}")
            raise

    async def _download_file(self, url: str) -> bytes:
        """Download a file and return its content."""
        response = await asyncio.to_thread(self.session.get, url, stream=True)

        chunks = []
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                chunks.append(chunk)

        return b"".join(chunks)


# Global processor instance
_processor = None


def get_mineru_processor() -> MinerUProcessor:
    """Get or create the global MinerU processor instance."""
    global _processor
    if _processor is None:
        _processor = MinerUProcessor()
        # Authenticate on first use
        _processor.login(use_saved=True)
    return _processor


@task(name="process_document_with_mineru", retries=2)
async def process_document_with_mineru(
    pdf_url: str, fdd_id: UUID, franchise_name: str, timeout_seconds: int = 300
) -> Dict[str, Any]:
    """
    Process a PDF document using MinerU Web API.

    Args:
        pdf_url: URL of the PDF to process
        fdd_id: FDD document ID
        franchise_name: Name of the franchise
        timeout_seconds: Processing timeout

    Returns:
        Dictionary with processing results and Google Drive file IDs
    """
    logger = PipelineLogger("process_document_with_mineru").bind(fdd_id=str(fdd_id))

    try:
        logger.info(
            "Starting MinerU document processing",
            pdf_url=pdf_url,
            franchise_name=franchise_name,
        )

        processor = get_mineru_processor()

        # Process with MinerU and store in Google Drive
        results = await processor.process_pdf_with_storage(
            pdf_url=pdf_url,
            fdd_uuid=fdd_id,
            franchise_name=franchise_name,
            wait_time=timeout_seconds,
        )

        logger.info(
            "MinerU processing completed",
            task_id=results["task_id"],
            markdown_file_id=results["drive_files"].get("markdown", {}).get("file_id"),
            json_file_id=results["drive_files"].get("json", {}).get("file_id"),
        )

        return results

    except Exception as e:
        logger.error("MinerU processing failed", error=str(e), pdf_url=pdf_url)
        raise


@task(name="extract_sections_from_mineru", retries=1)
async def extract_sections_from_mineru(
    mineru_results: Dict[str, Any], fdd_id: UUID
) -> List[FDDSection]:
    """
    Extract FDD sections from MinerU processing results.

    This is a placeholder that returns basic section info.
    The actual section detection happens in the enhanced detector.

    Args:
        mineru_results: Results from MinerU processing
        fdd_id: FDD document ID

    Returns:
        List of FDD sections (basic structure)
    """
    logger = PipelineLogger("extract_sections_from_mineru").bind(fdd_id=str(fdd_id))

    try:
        # For now, return a single section covering the whole document
        # The enhanced detector will handle actual section detection
        sections = [
            FDDSection(
                fdd_id=fdd_id,
                item_no=0,
                item_name="Complete Document",
                start_page=1,
                end_page=1,  # Will be updated by enhanced detector
                page_count=1,
                mineru_json_path=mineru_results["drive_files"]
                .get("json", {})
                .get("drive_path"),
                extraction_status="pending",
                confidence_score=1.0,
            )
        ]

        logger.info(
            "Created placeholder sections for MinerU results",
            section_count=len(sections),
        )

        return sections

    except Exception as e:
        logger.error("Failed to extract sections from MinerU", error=str(e))
        raise


if __name__ == "__main__":
    """Demonstrate MinerU processing functionality."""
    import sys
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def demo_mineru():
        """Run MinerU processing demos."""
        print("\n" + "="*60)
        print("MinerU Processing Module Demo")
        print("="*60 + "\n")
        
        # Demo 1: Initialize Processor
        print("1. Initializing MinerU Processor...")
        processor = MinerUProcessor()
        print(f"   ✓ Processor initialized")
        print(f"   Login URL: {processor.login_url}")
        print(f"   Auth file: {processor.auth_file}")
        
        # Demo 2: Check Authentication
        print("\n2. Authentication Status:")
        if processor.auth_file.exists():
            print(f"   ✓ Auth file exists: {processor.auth_file}")
            
            # Try to load saved auth
            try:
                with open(processor.auth_file, "r") as f:
                    auth_data = json.load(f)
                    has_token = any(c.get("name") == "uaa-token" for c in auth_data.get("cookies", []))
                    print(f"   Auth token present: {has_token}")
            except Exception as e:
                print(f"   ✗ Error reading auth file: {e}")
        else:
            print("   ✗ No saved authentication found")
            print("   Run processor.login() to authenticate")
        
        # Demo 3: Mock PDF Processing (without actual API calls)
        print("\n3. Mock PDF Processing Flow:")
        
        test_pdf_url = "https://example.com/test_fdd.pdf"
        test_fdd_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_franchise = "Test Franchise LLC"
        
        print(f"   PDF URL: {test_pdf_url}")
        print(f"   FDD UUID: {test_fdd_uuid}")
        print(f"   Franchise: {test_franchise}")
        
        print("\n   Processing steps:")
        print("   1. Submit PDF to MinerU API")
        print("   2. Poll for completion (check status every 10s)")
        print("   3. Download results (markdown and JSON)")
        print("   4. Upload to Google Drive")
        print("   5. Return processing results")
        
        # Demo 4: API Endpoints
        print("\n4. MinerU API Endpoints:")
        print(f"   Submit: {processor.api_submit}")
        print(f"   Tasks: {processor.api_tasks}")
        print(f"   Detail: {processor.api_detail.replace('{task_id}', '<task_id>')}")
        
        # Demo 5: Error Scenarios
        print("\n5. Common Error Scenarios:")
        error_scenarios = [
            ("No authentication", "Call processor.login() first"),
            ("Auth expired", "Saved auth token no longer valid"),
            ("Processing timeout", "PDF takes > 300s to process"),
            ("API error", "MinerU service returns error status"),
            ("Network error", "Connection issues during download"),
            ("Drive upload error", "Google Drive quota exceeded")
        ]
        
        for error, solution in error_scenarios:
            print(f"   • {error}: {solution}")
        
        # Demo 6: Live Test (Optional)
        print("\n6. Live API Test:")
        
        if len(sys.argv) > 1 and sys.argv[1] == "--live":
            print("   Running live test...")
            
            # Check if authenticated
            if not processor.auth_token:
                print("   Attempting login...")
                try:
                    success = processor.login(use_saved=True)
                    if success:
                        print("   ✓ Login successful!")
                    else:
                        print("   ✗ Login failed")
                        return
                except Exception as e:
                    print(f"   ✗ Login error: {e}")
                    return
            
            # Test with a real PDF URL if provided
            if len(sys.argv) > 2:
                test_url = sys.argv[2]
                print(f"\n   Processing PDF: {test_url}")
                
                try:
                    results = await processor.process_pdf_with_storage(
                        pdf_url=test_url,
                        fdd_uuid=test_fdd_uuid,
                        franchise_name=test_franchise,
                        wait_time=300
                    )
                    
                    print("\n   ✓ Processing completed!")
                    print(f"   Task ID: {results['task_id']}")
                    print(f"   Files stored: {len(results['drive_files'])}")
                    
                    for file_type, file_info in results['drive_files'].items():
                        print(f"   - {file_type}: {file_info['file_id']} ({file_info['size']:,} bytes)")
                    
                except Exception as e:
                    print(f"\n   ✗ Processing failed: {e}")
            else:
                print("   Provide a PDF URL as second argument for live test")
        else:
            print("   Run with --live flag to test API")
            print("   Example: python mineru_processing.py --live https://example.com/fdd.pdf")
        
        # Demo 7: Prefect Task Usage
        print("\n7. Prefect Task Usage:")
        print("   ```python")
        print("   from processing.mineru.mineru_processing import process_document_with_mineru")
        print("   ")
        print("   # In your Prefect flow:")
        print("   results = await process_document_with_mineru(")
        print("       pdf_url='https://example.com/fdd.pdf',")
        print("       fdd_id=fdd_uuid,")
        print("       franchise_name='Example Franchise',")
        print("       timeout_seconds=300")
        print("   )")
        print("   ```")
        
        print("\n" + "="*60)
        print("Demo completed!")
        print("="*60 + "\n")
    
    # Run the demo
    asyncio.run(demo_mineru())
