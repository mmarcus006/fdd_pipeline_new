# Troubleshooting Guide

## Overview

This guide provides solutions for common issues encountered with the FDD Pipeline, including diagnostic procedures, resolution steps, and preventive measures.

## Quick Diagnostics

### Health Check Script
```bash
# Run comprehensive health check
python scripts/health_check.py

# Sample output:
# ✓ Prefect server: Connected
# ✓ Database: Connected (42ms latency)
# ✓ Google Drive: Authenticated
# ✓ Email: Configuration valid
# ✗ ChromeDriver: Not found in PATH
# ✓ Disk space: 15.2 GB available
# ✓ Python packages: All installed
```

### System Status Commands
```bash
# Check Prefect status
prefect server health-check
prefect deployment ls
prefect work-pool ls

# Check recent logs
tail -f logs/fdd_pipeline.log | grep ERROR

# Database connectivity
python -c "from src.utils.database import test_connection; test_connection()"

# Review recent errors
python scripts/error_summary.py --hours 24
```

## Common Issues and Solutions

### 1. Scraping Failures

#### Issue: "Element not found" errors
**Symptoms:**
- Playwright TimeoutError
- "Unable to locate element" in logs
- Specific state portals failing consistently

**Diagnosis:**
```python
# Test specific state scraper
python -m franchise_scrapers.mn.scraper --test-mode

# Check page structure
python scripts/wisconsin_table_extractor.py --analyze
```

**Solutions:**
1. Update selectors:
   ```python
   # franchise_scrapers/wi/search.py
   SELECTORS = {
       'search_input': '#txtName',  # Updated from #ctl00_contentPlaceholder_txtSearch
       'search_button': '#btnSearch',  # Updated from button with "(S)earch" text
       'results_table': '#ctl00_contentPlaceholder_grdSearchResults'
   }
   ```

2. Increase timeouts:
   ```python
   # franchise_scrapers/browser.py
   context.set_default_timeout(30000)  # 30 seconds
   context.set_default_navigation_timeout(30000)  # 30 seconds
   ```

3. Add retry logic:
   ```python
   # franchise_scrapers/browser.py
   async def with_retry(coro, *args, max_attempts=3, delays=[1.0, 2.0, 4.0], **kwargs):
       for attempt in range(max_attempts):
           try:
               return await coro(*args, **kwargs)
           except Exception as exc:
               if attempt >= max_attempts - 1:
                   raise
               await sleep(delays[min(attempt, len(delays) - 1)])
   ```

#### Issue: "Access denied" or rate limiting
**Symptoms:**
- 403 Forbidden responses
- "Too many requests" messages
- IP blocked temporarily

**Solutions:**
1. Implement delays:
   ```python
   # franchise_scrapers/config.py
   THROTTLE_SEC = 0.5  # Default delay between requests
   # Can be overridden with environment variable
   ```

2. Configure user agent:
   ```python
   # franchise_scrapers/browser.py
   context = await browser.new_context(
       viewport={'width': 1280, 'height': 720},
       user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
       accept_downloads=True,
   )
   ```

3. Use proxy rotation (if necessary):
   ```python
   # config/proxy_config.py
   PROXY_LIST = [
       'http://proxy1.example.com:8080',
       'http://proxy2.example.com:8080',
   ]
   ```

### 2. Database Issues

#### Issue: Connection timeouts to Supabase
**Symptoms:**
- "Connection timeout" errors
- "SSL connection has been closed unexpectedly"
- Intermittent failures

**Diagnosis:**
```bash
# Test connection
python scripts/health_check.py --check database

# Check network latency
ping your-project.supabase.co

# Verify credentials
python -c "import os; print(os.getenv('SUPABASE_URL'))"
```

**Solutions:**
1. Implement connection pooling:
   ```python
   # src/utils/database.py
   from supabase import create_client
   from urllib3.util.retry import Retry
   
   class DatabaseConnection:
       def __init__(self):
           self.client = None
           self.retry_strategy = Retry(
               total=3,
               backoff_factor=1,
               status_forcelist=[429, 500, 502, 503, 504]
           )
       
       def get_client(self):
           if not self.client:
               self.client = create_client(
                   os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_KEY')
               )
           return self.client
   ```

2. Add connection retry logic:
   ```python
   @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
   def execute_query(self, query):
       return self.client.table('pipeline_logs').insert(query).execute()
   ```

3. Handle connection drops:
   ```python
   def safe_insert(self, data):
       try:
           return self.execute_query(data)
       except Exception as e:
           logger.error(f"Database error: {e}")
           self.client = None  # Force reconnection
           return self.execute_query(data)
   ```

#### Issue: Data insertion failures
**Symptoms:**
- "Duplicate key" errors
- "Invalid input syntax" errors
- Partial data saved

**Solutions:**
1. Add data validation:
   ```python
   # models/fdd.py - Using Pydantic validation
   class FDDCreate(FDDBase):
       filing_year: int = Field(..., ge=2000, le=datetime.now().year)
       state_code: str = Field(..., regex='^[A-Z]{2}$')
       pdf_url: HttpUrl
       pdf_hash: Optional[str] = Field(None, regex='^[a-f0-9]{64}$')
       
       @validator('filing_year')
       def validate_filing_year(cls, v):
           if v > datetime.now().year:
               raise ValueError('Filing year cannot be in the future')
           return v
   ```

2. Implement upsert logic:
   ```python
   # storage/database/manager.py
   async def upsert_fdd(self, fdd_data: dict) -> dict:
       return await self.client.table('fdds')\
           .upsert(
               fdd_data,
               on_conflict='franchisor_id,filing_year,state_code',
               returning='representation'
           ).execute()
   ```

### 3. Prefect Flow Issues

#### Issue: Flows not starting on schedule
**Symptoms:**
- Scheduled runs not appearing
- "No workers available" messages
- Deployments show as inactive

**Diagnosis:**
```bash
# Check deployment status
prefect deployment inspect minnesota-fdd-scraper/production

# Verify schedules
prefect deployment schedule ls minnesota-fdd-scraper/production

# Check worker status
prefect work-pool inspect default-agent-pool
```

**Solutions:**
1. Restart worker:
   ```bash
   # Find and kill existing worker
   ps aux | grep "prefect worker"
   kill -TERM <worker-pid>
   
   # Start new worker
   prefect worker start --pool default-agent-pool --limit 1
   ```

2. Fix timezone issues:
   ```bash
   # Update schedule with correct timezone
   prefect deployment schedule delete minnesota-fdd-scraper/production <schedule-id>
   prefect deployment schedule create minnesota-fdd-scraper/production \
     --cron "0 2 * * 1" \
     --timezone "America/Chicago"
   ```

3. Re-deploy flows:
   ```bash
   python scripts/deploy_state_flows.py --state mn --force
   ```

#### Issue: Flow runs hanging or timing out
**Symptoms:**
- Flows stuck in "Running" state
- No logs being generated
- Worker unresponsive

**Solutions:**
1. Add flow timeouts:
   ```python
   # workflows/base_state_flow.py
   from prefect import flow
   from datetime import timedelta
   
   @flow(
       name="{state_name}-fdd-scraper",
       timeout_seconds=7200,  # 2 hours
       retries=2,
       retry_delay_seconds=300
   )
   async def create_state_flow(config: StateConfig):
       pass
   ```

2. Implement task-level timeouts:
   ```python
   @task(timeout_seconds=300)  # 5 minutes per FDD
   async def download_fdd(page: Page, row: CleanFDDRow) -> CleanFDDRow:
       pass
   ```

3. Add progress monitoring:
   ```python
   @task
   async def download_pdfs(rows: List[CleanFDDRow], page: Page) -> List[CleanFDDRow]:
       for i, row in enumerate(rows, 1):
           logger.info(f"Processing {i}/{len(rows)}: {row.legal_name}")
           yield await download_pdf(page, row)
   ```

### 4. Google Drive Issues

#### Issue: Authentication failures
**Symptoms:**
- "Invalid credentials" errors
- "Token has been expired or revoked"
- 401 Unauthorized responses

**Solutions:**
1. Refresh service account:
   ```bash
   # Verify service account file
   python storage/authenticate_gdrive.py
   
   # Check permissions
   python scripts/setup_gdrive_structure.py --check-only
   ```

2. Re-authenticate:
   ```python
   # storage/google_drive.py
   def __init__(self, use_oauth2: bool = False):
       if use_oauth2:
           creds = self._get_oauth2_credentials()
       else:
           creds = service_account.Credentials.from_service_account_file(
               settings.GDRIVE_CREDS_JSON,
               scopes=['https://www.googleapis.com/auth/drive']
           )
       self.service = build('drive', 'v3', credentials=creds)
   ```

#### Issue: Upload failures
**Symptoms:**
- "Insufficient permissions" errors
- Timeouts during upload
- Files not appearing in Drive

**Solutions:**
1. Check folder permissions:
   ```python
   def verify_folder_access(folder_id):
       service = get_drive_service()
       try:
           folder = service.files().get(fileId=folder_id).execute()
           print(f"Folder accessible: {folder['name']}")
           return True
       except Exception as e:
           print(f"Cannot access folder: {e}")
           return False
   ```

2. Implement chunked uploads:
   ```python
   # src/utils/drive_upload.py
   from googleapiclient.http import MediaFileUpload
   
   def upload_large_file(file_path, folder_id):
       media = MediaFileUpload(
           file_path,
           mimetype='text/csv',
           resumable=True,
           chunksize=1024*1024  # 1MB chunks
       )
       
       request = service.files().create(
           body=file_metadata,
           media_body=media
       )
       
       response = None
       while response is None:
           status, response = request.next_chunk()
           if status:
               print(f"Upload {int(status.progress() * 100)}%")
   ```

### 5. Performance Issues

#### Issue: Slow scraping performance
**Symptoms:**
- FDD downloads taking >1 minute each
- Total runtime >3 hours for a state
- Memory usage increasing

**Diagnosis:**
```python
# Profile scraping performance
python -m cProfile -o profile.stats franchise_scrapers/mn/scraper.py --test
python scripts/analyze_profile.py profile.stats
```

**Solutions:**
1. Implement parallel processing:
   ```python
   # franchise_scrapers/wi/search.py
   async def search_wi_franchises(active_rows: List[WIActiveRow], max_workers: int = None):
       if max_workers is None:
           max_workers = settings.MAX_WORKERS
       
       # Process franchises in batches
       for i in range(0, len(active_rows), max_workers):
           batch = active_rows[i:i + max_workers]
           tasks = [
               search_single_franchise(browser, active_row)
               for active_row in batch
           ]
           results = await asyncio.gather(*tasks, return_exceptions=True)
   ```

2. Optimize selectors:
   ```python
   # Use specific IDs when available
   # Instead of: 'button:has-text("Load more")'
   # Use: '#pagination button.btn.btn-primary'
   
   async def click_load_more(page: Page) -> bool:
       button = await page.query_selector("#pagination button.btn.btn-primary")
       if button and await button.is_visible():
           await button.click()
   ```

3. Cache static data:
   ```python
   # franchise_scrapers/models.py
   from functools import lru_cache
   
   @lru_cache(maxsize=1000)
   def get_cached_franchise_data(franchise_name: str, state: str):
       # Cache franchise lookups during session
       return search_franchise_in_db(franchise_name, state)
   ```

### 6. Email Alert Issues

#### Issue: Alerts not being sent
**Symptoms:**
- No email notifications for failures
- "Authentication failed" in logs
- SMTP connection errors

**Solutions:**
1. Test email configuration:
   ```bash
   python scripts/test_email.py --recipient test@example.com
   ```

2. Update SMTP settings:
   ```python
   # For Gmail with app password
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-specific-password  # Not regular password
   ```

3. Implement fallback notification:
   ```python
   # src/utils/notifications.py
   def send_notification(subject, body):
       try:
           send_email(subject, body)
       except Exception as e:
           logger.error(f"Email failed: {e}")
           # Fallback to local logging
           with open('alerts.log', 'a') as f:
               f.write(f"{datetime.now()}: {subject}\n{body}\n\n")
   ```

## Advanced Troubleshooting

### Memory Leaks

**Detection:**
```python
# scripts/memory_monitor.py
import psutil
import os

def monitor_memory():
    process = psutil.Process(os.getpid())
    while True:
        mem_info = process.memory_info()
        print(f"RSS: {mem_info.rss / 1024 / 1024:.2f} MB")
        time.sleep(10)
```

**Solutions:**
1. Properly close browser instances:
   ```python
   def scrape_with_cleanup(url):
       driver = None
       try:
           driver = create_driver()
           # Scraping logic
       finally:
           if driver:
               driver.quit()
   ```

2. Clear large objects:
   ```python
   def process_large_dataset(data):
       # Process data
       results = analyze_data(data)
       
       # Clear reference
       del data
       gc.collect()
       
       return results
   ```

### Debugging Techniques

#### Enable Debug Logging
```python
# config/logging_config.py
import logging

# Set all loggers to DEBUG
logging.basicConfig(level=logging.DEBUG)

# Enable Selenium debug logs
logging.getLogger('selenium').setLevel(logging.DEBUG)

# Enable database query logs
logging.getLogger('supabase').setLevel(logging.DEBUG)
```

#### Interactive Debugging
```python
# scripts/debug_scraper.py
import pdb
from src.scrapers import MinnesotaScraper

def debug_scrape():
    scraper = MinnesotaScraper()
    
    # Set breakpoint
    pdb.set_trace()
    
    # Step through scraping
    results = scraper.scrape_department("Computer Science")
    
    return results

if __name__ == "__main__":
    debug_scrape()
```

#### Network Debugging
```bash
# Monitor network requests
mitmdump -s scripts/log_requests.py

# Check DNS resolution
nslookup your-project.supabase.co

# Test connectivity
curl -I https://your-project.supabase.co
```

## Prevention Strategies

### 1. Automated Testing
```python
# tests/scrapers/states/test_minnesota.py
import pytest
from franchise_scrapers.mn.scraper import scrape_minnesota

@pytest.mark.asyncio
async def test_minnesota_scraper():
    # Test with limited pages
    rows = await scrape_minnesota(download_pdfs=False, max_pages=1)
    assert len(rows) > 0
    assert all(hasattr(row, 'document_id') for row in rows)
    assert all(hasattr(row, 'legal_name') for row in rows)

@pytest.mark.asyncio
async def test_pdf_download():
    # Test single PDF download
    rows = await scrape_minnesota(download_pdfs=True, max_pages=1)
    successful = [r for r in rows if r.pdf_status == 'ok']
    assert len(successful) > 0
```

### 2. Health Monitoring
```python
# scripts/continuous_monitor.py
#!/usr/bin/env python3
import time
from datetime import datetime, timedelta

async def monitor_pipeline_health():
    while True:
        try:
            # Check last successful FDD scrape
            check_last_fdd_scrape()
            
            # Monitor MinerU API status
            check_mineru_health()
            
            # Verify Google Drive quota
            check_gdrive_quota()
            
        except Exception as e:
            send_alert(f"Monitor failed: {e}")
        
        await asyncio.sleep(300)  # Check every 5 minutes
```

### 3. Graceful Degradation
```python
# franchise_scrapers/mn/scraper.py
async def scrape_all_pages(page: Page, max_pages: int = 50) -> List[Dict[str, Any]]:
    all_data = []
    page_num = 1
    
    while page_num <= max_pages:
        try:
            current_data = await extract_table_data(page)
            all_data.extend(current_data)
            
            if not await click_load_more(page):
                break
                
        except Exception as e:
            logger.error(f"Failed on page {page_num}: {e}")
            # Continue with next page instead of failing entirely
            
        page_num += 1
        await asyncio.sleep(settings.THROTTLE_SEC)
    
    return all_data
```

## Emergency Procedures

### Complete System Failure
1. **Immediate Actions:**
   ```bash
   # Stop all processes
   pkill -f prefect
   pkill -f python
   
   # Check system resources
   df -h
   free -m
   ps aux | sort -nrk 3,3 | head -10
   ```

2. **Diagnostic Steps:**
   ```bash
   # Review recent errors
   tail -n 1000 logs/fdd_pipeline_errors.log
   
   # Check database connectivity
   python -c "from storage.database.manager import DatabaseManager; db = DatabaseManager(); print(db.test_connection())"
   
   # Verify external services
   curl -I https://www.cards.commerce.state.mn.us
   curl -I https://apps.dfi.wi.gov
   ```

3. **Recovery Steps:**
   ```bash
   # Clear temporary files
   rm -rf /tmp/selenium*
   rm -rf logs/*.log.*
   
   # Reset Prefect
   prefect server database reset -y
   
   # Redeploy flows
   ./scripts/redeploy_all.sh
   
   # Start fresh
   prefect server start &
   prefect worker start --pool fdd-local-pool &
   ```

### Data Recovery
```python
# scripts/recover_partial_data.py
async def recover_incomplete_scrape():
    # Find incomplete FDD scrapes
    incomplete = await db.query("""
        SELECT DISTINCT flow_run_id, state_code
        FROM pipeline_logs
        WHERE log_type = 'scrape_started'
        AND flow_run_id NOT IN (
            SELECT flow_run_id 
            FROM pipeline_logs 
            WHERE log_type = 'scrape_completed'
        )
        AND created_at > NOW() - INTERVAL '24 hours'
    """)
    
    # Attempt to recover FDD data
    for run in incomplete:
        partial_data = await db.query(f"""
            SELECT * FROM fdds
            WHERE metadata->>'flow_run_id' = '{run['flow_run_id']}'
        """)
        
        if partial_data:
            await save_to_backup(partial_data)
            logger.info(f"Recovered {len(partial_data)} FDDs from {run['flow_run_id']}")
```

## Support Escalation

### Level 1: Self-Service
- Review this troubleshooting guide
- Check recent deployments for changes
- Run diagnostic scripts
- Review monitoring dashboards

### Level 2: Team Support
- Post in #fdd-pipeline-support Slack channel
- Include error logs and diagnostic output
- Tag on-call engineer if urgent

### Level 3: External Support
- Prefect Cloud support (for Prefect issues)
- Supabase support (for database issues)
- Google Cloud support (for Drive API issues)

### Creating Support Tickets
Include:
1. Error messages and stack traces
2. Time of occurrence
3. Recent changes or deployments
4. Diagnostic script output
5. Steps to reproduce
6. Impact assessment

## Appendix: Useful Commands

### Quick Diagnostics
```bash
# One-liner health check
python scripts/health_check.py --all

# Recent errors summary
grep -E "(ERROR|CRITICAL)" logs/fdd_pipeline.log | tail -20 | cut -d' ' -f5- | sort | uniq -c

# Performance check
python scripts/monitoring.py --metrics --period 24h

# Test specific state scraper
python -m franchise_scrapers.mn.scraper --test --max-pages 1

# Force cleanup
rm -rf franchise_scrapers/downloads/*/temp_*
```

### Recovery Commands
```bash
# Reset stuck flow
prefect flow-run cancel <flow-run-id>

# Clear work pool
prefect work-pool clear default-agent-pool

# Restart state scrape
python main.py scrape --state mn --resume

# Emergency FDD export
python -c "from storage.database.manager import DatabaseManager; db = DatabaseManager(); db.export_fdds('backup.csv')"