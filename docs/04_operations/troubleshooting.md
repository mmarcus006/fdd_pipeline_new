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
- Selenium TimeoutException
- "Unable to locate element" in logs
- Specific departments failing consistently

**Diagnosis:**
```python
# Test specific department
python scripts/test_scrape.py --university mn --department "Computer Science" --verbose

# Check page structure
python scripts/analyze_page.py --url "https://example.edu/directory"
```

**Solutions:**
1. Update selectors:
   ```python
   # src/scrapers/element_selectors.py
   SELECTORS = {
       'mn': {
           'faculty_list': '//div[@class="faculty-listing"]',  # Old
           'faculty_list': '//div[@class="staff-directory"]',  # New
       }
   }
   ```

2. Increase timeouts:
   ```python
   # config/scraper_config.py
   ELEMENT_TIMEOUT = 30  # Increase from 20
   PAGE_LOAD_TIMEOUT = 45  # Increase from 30
   ```

3. Add retry logic:
   ```python
   # src/scrapers/base_scraper.py
   @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2))
   def find_element_safe(self, selector):
       return self.driver.find_element(By.XPATH, selector)
   ```

#### Issue: "Access denied" or rate limiting
**Symptoms:**
- 403 Forbidden responses
- "Too many requests" messages
- IP blocked temporarily

**Solutions:**
1. Implement delays:
   ```python
   # config/scraper_config.py
   REQUEST_DELAY = 2  # Seconds between requests
   DEPARTMENT_DELAY = 5  # Seconds between departments
   ```

2. Add user agent rotation:
   ```python
   # src/scrapers/browser_config.py
   USER_AGENTS = [
       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
       'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
   ]
   
   options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
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
python scripts/test_database.py

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
   # src/utils/validators.py
   def validate_faculty_data(data):
       required_fields = ['name', 'department', 'university']
       for field in required_fields:
           if field not in data or not data[field]:
               raise ValueError(f"Missing required field: {field}")
       
       # Email validation
       if 'email' in data and data['email']:
           if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', data['email']):
               data['email'] = None
       
       return data
   ```

2. Implement upsert logic:
   ```python
   # src/utils/database_operations.py
   def upsert_faculty(self, faculty_data):
       return self.client.table('faculty')\
           .upsert(
               faculty_data,
               on_conflict='email,university',
               returning='minimal'
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
prefect deployment inspect minnesota-scrape/prod

# Verify schedules
prefect deployment schedule ls minnesota-scrape/prod

# Check worker status
prefect work-pool inspect fdd-local-pool
```

**Solutions:**
1. Restart worker:
   ```bash
   # Find and kill existing worker
   ps aux | grep "prefect worker"
   kill -TERM <worker-pid>
   
   # Start new worker
   prefect worker start --pool fdd-local-pool --limit 1
   ```

2. Fix timezone issues:
   ```bash
   # Update schedule with correct timezone
   prefect deployment schedule delete minnesota-scrape/prod <schedule-id>
   prefect deployment schedule create minnesota-scrape/prod \
     --cron "0 2 * * 1" \
     --timezone "America/Chicago"
   ```

3. Re-deploy flows:
   ```bash
   python deployments/deploy_mn_flow.py --force
   ```

#### Issue: Flow runs hanging or timing out
**Symptoms:**
- Flows stuck in "Running" state
- No logs being generated
- Worker unresponsive

**Solutions:**
1. Add flow timeouts:
   ```python
   # src/flows/scraper_flow.py
   from prefect import flow
   from datetime import timedelta
   
   @flow(
       name="minnesota-scrape",
       timeout_seconds=7200,  # 2 hours
       retries=2,
       retry_delay_seconds=300
   )
   def scrape_minnesota():
       pass
   ```

2. Implement task-level timeouts:
   ```python
   @task(timeout_seconds=300)  # 5 minutes per department
   def scrape_department(url, department):
       pass
   ```

3. Add progress monitoring:
   ```python
   @task
   def scrape_with_progress(departments):
       for i, dept in enumerate(departments):
           logger.info(f"Processing {i+1}/{len(departments)}: {dept}")
           yield scrape_department(dept)
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
   python scripts/test_google_auth.py
   
   # Check permissions
   python scripts/check_drive_permissions.py --folder-id $GOOGLE_DRIVE_FOLDER_ID
   ```

2. Re-authenticate:
   ```python
   # src/utils/google_drive.py
   def get_drive_service():
       creds = service_account.Credentials.from_service_account_file(
           os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH'),
           scopes=['https://www.googleapis.com/auth/drive']
       )
       return build('drive', 'v3', credentials=creds)
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
- Departments taking >1 minute each
- Total runtime >3 hours
- Memory usage increasing

**Diagnosis:**
```python
# Profile scraping performance
python -m cProfile -o profile.stats scripts/test_scrape.py
python scripts/analyze_profile.py profile.stats
```

**Solutions:**
1. Implement parallel processing:
   ```python
   # src/scrapers/parallel_scraper.py
   from concurrent.futures import ThreadPoolExecutor
   
   def scrape_departments_parallel(departments, max_workers=4):
       with ThreadPoolExecutor(max_workers=max_workers) as executor:
           futures = []
           for dept in departments:
               future = executor.submit(scrape_department, dept)
               futures.append(future)
           
           results = []
           for future in as_completed(futures):
               try:
                   result = future.result(timeout=300)
                   results.append(result)
               except TimeoutError:
                   logger.error(f"Department scrape timed out")
       
       return results
   ```

2. Optimize selectors:
   ```python
   # Use CSS selectors when faster
   # Instead of: //div[@class='faculty']//span[@class='name']
   # Use: div.faculty span.name
   
   def get_faculty_names(self):
       return self.driver.find_elements(By.CSS_SELECTOR, "div.faculty span.name")
   ```

3. Cache static data:
   ```python
   # src/utils/cache.py
   from functools import lru_cache
   
   @lru_cache(maxsize=100)
   def get_department_list(university):
       # Cache department lists for 24 hours
       return scrape_department_list(university)
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
# tests/test_scrapers.py
import pytest
from src.scrapers import MinnesotaScraper

@pytest.fixture
def scraper():
    return MinnesotaScraper()

def test_department_list(scraper):
    departments = scraper.get_departments()
    assert len(departments) > 0
    assert all('name' in dept for dept in departments)

def test_faculty_scrape(scraper):
    faculty = scraper.scrape_department("Computer Science")
    assert len(faculty) > 0
    assert all('email' in f for f in faculty)
```

### 2. Health Monitoring
```python
# scripts/continuous_monitor.py
#!/usr/bin/env python3
import time
from datetime import datetime, timedelta

def monitor_pipeline_health():
    while True:
        try:
            # Check last successful run
            check_last_run()
            
            # Monitor error rate
            check_error_rate()
            
            # Verify system resources
            check_system_health()
            
        except Exception as e:
            send_alert(f"Monitor failed: {e}")
        
        time.sleep(300)  # Check every 5 minutes
```

### 3. Graceful Degradation
```python
# src/scrapers/resilient_scraper.py
class ResilientScraper:
    def scrape_all_departments(self):
        results = []
        failed_departments = []
        
        for dept in self.get_departments():
            try:
                data = self.scrape_department(dept)
                results.extend(data)
            except Exception as e:
                logger.error(f"Failed to scrape {dept}: {e}")
                failed_departments.append(dept)
                continue  # Continue with next department
        
        # Report partial success
        if failed_departments:
            self.report_failures(failed_departments)
        
        return results
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
   psql $DATABASE_URL -c "SELECT 1"
   
   # Verify external services
   curl -I https://www.umn.edu
   curl -I https://www.wisconsin.edu
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
def recover_incomplete_scrape():
    # Find incomplete runs
    incomplete = db.query("""
        SELECT DISTINCT flow_run_id, university
        FROM pipeline_logs
        WHERE log_type = 'flow_started'
        AND flow_run_id NOT IN (
            SELECT flow_run_id 
            FROM pipeline_logs 
            WHERE log_type = 'flow_completed'
        )
        AND created_at > NOW() - INTERVAL '24 hours'
    """)
    
    # Attempt to recover data
    for run in incomplete:
        partial_data = db.query(f"""
            SELECT * FROM scraped_data
            WHERE flow_run_id = '{run['flow_run_id']}'
        """)
        
        if partial_data:
            save_to_backup(partial_data)
            logger.info(f"Recovered {len(partial_data)} records from {run['flow_run_id']}")
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
python -c "from scripts.health_check import run_all_checks; run_all_checks()"

# Recent errors summary
grep -E "(ERROR|CRITICAL)" logs/fdd_pipeline.log | tail -20 | cut -d' ' -f5- | sort | uniq -c

# Performance check
python -c "from src.utils.database import get_metrics; print(get_metrics('24h'))"

# Test specific university
python -m src.scrapers.test_scraper --university mn --quick

# Force cleanup
python scripts/cleanup.py --force --all
```

### Recovery Commands
```bash
# Reset stuck flow
prefect flow-run cancel <flow-run-id>

# Clear queue
prefect work-queue clear fdd-local-queue

# Restart from checkpoint
python scripts/resume_scrape.py --flow-run-id <id> --from-checkpoint

# Emergency data export
python scripts/export_all_data.py --format csv --output /backup/
```