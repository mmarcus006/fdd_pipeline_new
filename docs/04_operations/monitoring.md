# Monitoring Guide

## Overview

This guide covers monitoring setup, key metrics, alerting, and observability for the FDD Pipeline. Effective monitoring ensures reliable operation and quick issue detection.

## Monitoring Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Prefect UI    │────►│   Supabase   │────►│   Alerts    │
│  (Flow Runs)    │     │  (Log Store) │     │   (Email)   │
└─────────────────┘     └──────────────┘     └─────────────┘
         │                      │                     │
         ▼                      ▼                     ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Local Logs    │     │  Dashboards  │     │  PagerDuty  │
│   (Rotating)    │     │  (Grafana)   │     │  (Critical) │
└─────────────────┘     └──────────────┘     └─────────────┘
```

## Key Metrics

### Pipeline Health Metrics

#### 1. Extraction Success Rate
- **Target**: >95%
- **Formula**: Successful extractions / Total attempts
- **Alert Threshold**: <90% over 3 runs
- **Query**:
  ```sql
  SELECT 
    university,
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
  FROM pipeline_logs
  WHERE log_type = 'extraction'
    AND created_at > NOW() - INTERVAL '7 days'
  GROUP BY university, date
  ORDER BY date DESC;
  ```

#### 2. Processing Time
- **Target**: <2 hours per university
- **Components**:
  - Department listing: <5 minutes
  - Per department scrape: <30 seconds
  - Data processing: <10 minutes
  - Google Drive upload: <5 minutes
- **Alert Threshold**: >3 hours total
- **Query**:
  ```sql
  SELECT 
    flow_run_id,
    university,
    MIN(created_at) as start_time,
    MAX(created_at) as end_time,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))/60 as duration_minutes
  FROM pipeline_logs
  WHERE created_at > NOW() - INTERVAL '24 hours'
  GROUP BY flow_run_id, university
  HAVING COUNT(DISTINCT log_type) > 1
  ORDER BY start_time DESC;
  ```

#### 3. Data Quality Metrics
- **Record Completeness**: >98%
- **Email Validation Rate**: >95%
- **Department Coverage**: 100%
- **Query**:
  ```sql
  SELECT 
    university,
    COUNT(*) as total_records,
    SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) as with_email,
    SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) as with_phone,
    SUM(CASE WHEN department IS NOT NULL THEN 1 ELSE 0 END) as with_department,
    ROUND(100.0 * SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as email_rate
  FROM scraped_data
  WHERE created_at > NOW() - INTERVAL '7 days'
  GROUP BY university;
  ```

### System Health Metrics

#### 1. Resource Utilization
- **CPU Usage**: <70% sustained
- **Memory Usage**: <3GB
- **Disk Space**: >2GB free
- **Network Bandwidth**: <10Mbps

#### 2. Error Rates
- **Scraping Errors**: <5%
- **Database Errors**: <1%
- **API Errors**: <2%
- **Query**:
  ```sql
  SELECT 
    log_level,
    log_type,
    COUNT(*) as error_count,
    COUNT(DISTINCT flow_run_id) as affected_runs
  FROM pipeline_logs
  WHERE log_level IN ('ERROR', 'CRITICAL')
    AND created_at > NOW() - INTERVAL '24 hours'
  GROUP BY log_level, log_type
  ORDER BY error_count DESC;
  ```

## Monitoring Setup

### 1. Prefect UI Monitoring

Access at http://localhost:4200

**Key Views**:
- Flow Runs: Monitor active and recent runs
- Deployments: Check schedule adherence
- Work Pools: Verify worker health
- Notifications: Review recent alerts

**Custom Dashboards**:
```python
# Create custom workspace
prefect cloud workspace create fdd-pipeline-monitoring

# Set up automation
prefect automation create "Failed Run Alert" \
  --trigger "flow_run_state:failed" \
  --action "send_notification:email"
```

### 2. Database Monitoring

#### Create Monitoring Views
```sql
-- Pipeline performance view
CREATE VIEW v_pipeline_performance AS
SELECT 
  DATE_TRUNC('hour', created_at) as hour,
  university,
  log_type,
  COUNT(*) as event_count,
  AVG(CASE WHEN metric_value IS NOT NULL THEN metric_value END) as avg_duration,
  MAX(CASE WHEN metric_value IS NOT NULL THEN metric_value END) as max_duration
FROM pipeline_logs
GROUP BY hour, university, log_type;

-- Error summary view
CREATE VIEW v_error_summary AS
SELECT 
  DATE_TRUNC('day', created_at) as date,
  university,
  error_type,
  COUNT(*) as error_count,
  STRING_AGG(DISTINCT error_message, '; ') as sample_errors
FROM pipeline_logs
WHERE log_level IN ('ERROR', 'CRITICAL')
GROUP BY date, university, error_type;

-- Data quality view
CREATE VIEW v_data_quality AS
SELECT 
  scrape_date,
  university,
  COUNT(*) as total_records,
  COUNT(DISTINCT department) as unique_departments,
  SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) as valid_emails,
  SUM(CASE WHEN phone IS NOT NULL AND phone != '' THEN 1 ELSE 0 END) as valid_phones
FROM scraped_data
GROUP BY scrape_date, university;
```

#### Monitoring Queries
```sql
-- Real-time pipeline status
SELECT 
  flow_run_id,
  university,
  log_type,
  log_level,
  message,
  created_at
FROM pipeline_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 100;

-- Weekly performance report
SELECT 
  university,
  COUNT(DISTINCT flow_run_id) as total_runs,
  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
  AVG(duration_minutes) as avg_duration,
  MAX(duration_minutes) as max_duration
FROM (
  SELECT 
    flow_run_id,
    university,
    MAX(CASE WHEN log_type = 'flow_completed' THEN 'completed' ELSE 'failed' END) as status,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))/60 as duration_minutes
  FROM pipeline_logs
  WHERE created_at > NOW() - INTERVAL '7 days'
  GROUP BY flow_run_id, university
) runs
GROUP BY university;
```

### 3. Log Aggregation

#### Local Log Configuration
```python
# config/logging_config.py
import logging
from logging.handlers import RotatingFileHandler

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
        'json': {
            'format': '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/fdd_pipeline.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'json'
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/fdd_pipeline_errors.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'detailed',
            'level': 'ERROR'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'error_file']
    }
}
```

#### Log Analysis Scripts
```bash
# Count errors by type
grep ERROR logs/fdd_pipeline.log | jq '.message' | sort | uniq -c

# Extract performance metrics
grep "duration" logs/fdd_pipeline.log | jq '.duration' | awk '{sum+=$1} END {print "Average:", sum/NR}'

# Monitor real-time
tail -f logs/fdd_pipeline.log | jq '.'
```

### 4. Alert Configuration

#### Email Alert Setup
```python
# src/monitoring/alerts.py
from prefect import flow, task
from prefect.blocks.notifications import EmailServerCredentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class AlertManager:
    def __init__(self):
        self.smtp_config = {
            'host': os.getenv('SMTP_HOST'),
            'port': int(os.getenv('SMTP_PORT')),
            'username': os.getenv('SMTP_USERNAME'),
            'password': os.getenv('SMTP_PASSWORD')
        }
        
    def send_alert(self, subject, body, severity='WARNING'):
        msg = MIMEMultipart()
        msg['From'] = os.getenv('ALERT_EMAIL_FROM')
        msg['To'] = os.getenv('ALERT_EMAIL_TO')
        msg['Subject'] = f"[{severity}] FDD Pipeline: {subject}"
        
        # Add severity-based formatting
        if severity == 'CRITICAL':
            body = f"🚨 CRITICAL ALERT 🚨\n\n{body}"
        elif severity == 'ERROR':
            body = f"❌ ERROR ALERT ❌\n\n{body}"
        else:
            body = f"⚠️  WARNING ⚠️\n\n{body}"
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port']) as server:
            server.starttls()
            server.login(self.smtp_config['username'], self.smtp_config['password'])
            server.send_message(msg)
```

#### Alert Rules
```python
# config/alert_rules.py
ALERT_RULES = [
    {
        'name': 'Extraction Failure',
        'condition': 'extraction_success_rate < 90',
        'severity': 'ERROR',
        'message': 'Extraction success rate dropped below 90%'
    },
    {
        'name': 'Long Running Flow',
        'condition': 'flow_duration > 180',  # minutes
        'severity': 'WARNING',
        'message': 'Flow running longer than 3 hours'
    },
    {
        'name': 'Database Connection Lost',
        'condition': 'db_connection_error',
        'severity': 'CRITICAL',
        'message': 'Cannot connect to Supabase'
    },
    {
        'name': 'Disk Space Low',
        'condition': 'disk_free_space < 1000',  # MB
        'severity': 'ERROR',
        'message': 'Less than 1GB disk space remaining'
    }
]
```

## Dashboards

### 1. Grafana Setup (Optional)

```bash
# Install Grafana
docker run -d -p 3000:3000 --name=grafana grafana/grafana

# Configure PostgreSQL data source
# URL: your-supabase-url
# Database: postgres
# User: postgres
# Password: your-password
# SSL Mode: require
```

### 2. Dashboard Queries

#### Pipeline Overview Dashboard
```sql
-- Success rate gauge
SELECT 
  ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM pipeline_runs
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Run duration time series
SELECT 
  DATE_TRUNC('hour', start_time) as time,
  AVG(EXTRACT(EPOCH FROM (end_time - start_time))/60) as avg_duration_minutes
FROM pipeline_runs
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY time
ORDER BY time;

-- Error count by type
SELECT 
  error_type,
  COUNT(*) as count
FROM pipeline_errors
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY error_type;
```

### 3. Custom Monitoring Scripts

```python
# scripts/monitor_pipeline.py
#!/usr/bin/env python3
import asyncio
from datetime import datetime, timedelta
from src.utils.database import get_supabase_client
from src.monitoring.alerts import AlertManager

async def check_pipeline_health():
    client = get_supabase_client()
    alert_manager = AlertManager()
    
    # Check last run time
    last_run = client.table('pipeline_logs')\
        .select('created_at')\
        .order('created_at', desc=True)\
        .limit(1)\
        .execute()
    
    if last_run.data:
        last_run_time = datetime.fromisoformat(last_run.data[0]['created_at'])
        hours_since = (datetime.now() - last_run_time).seconds / 3600
        
        if hours_since > 24:
            alert_manager.send_alert(
                "No Recent Pipeline Activity",
                f"Last pipeline run was {hours_since:.1f} hours ago",
                severity='WARNING'
            )
    
    # Check error rate
    errors = client.table('pipeline_logs')\
        .select('*')\
        .eq('log_level', 'ERROR')\
        .gte('created_at', (datetime.now() - timedelta(hours=24)).isoformat())\
        .execute()
    
    if len(errors.data) > 10:
        alert_manager.send_alert(
            "High Error Rate Detected",
            f"Found {len(errors.data)} errors in the last 24 hours",
            severity='ERROR'
        )

if __name__ == "__main__":
    asyncio.run(check_pipeline_health())
```

## Operational Procedures

### Daily Monitoring Checklist
- [ ] Check Prefect UI for failed runs
- [ ] Review error logs for patterns
- [ ] Verify schedule adherence
- [ ] Check disk space availability
- [ ] Review performance metrics
- [ ] Validate data quality metrics

### Weekly Monitoring Tasks
- [ ] Generate performance report
- [ ] Review and tune alert thresholds
- [ ] Analyze error trends
- [ ] Check for security alerts
- [ ] Validate backup procedures
- [ ] Update monitoring documentation

### Monthly Monitoring Tasks
- [ ] Full system health check
- [ ] Performance baseline review
- [ ] Alert rule optimization
- [ ] Dashboard updates
- [ ] Monitoring tool updates
- [ ] Capacity planning review

## Troubleshooting Monitoring Issues

### Common Issues

1. **Missing Metrics**
   - Check database connectivity
   - Verify logging configuration
   - Ensure proper permissions

2. **False Alerts**
   - Review alert thresholds
   - Check for environmental factors
   - Validate metric calculations

3. **Dashboard Errors**
   - Verify data source configuration
   - Check query permissions
   - Review time range settings

### Debug Commands

```bash
# Check Prefect health
prefect server health-check

# Test database connection
python -c "from src.utils.database import test_connection; test_connection()"

# Verify log aggregation
tail -f logs/fdd_pipeline.log | grep ERROR

# Check alert configuration
python scripts/test_alerts.py
```

## Performance Tuning

### Query Optimization
```sql
-- Add indexes for common queries
CREATE INDEX idx_pipeline_logs_created_at ON pipeline_logs(created_at);
CREATE INDEX idx_pipeline_logs_flow_run_id ON pipeline_logs(flow_run_id);
CREATE INDEX idx_pipeline_logs_composite ON pipeline_logs(created_at, log_level, university);

-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM pipeline_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
  AND log_level = 'ERROR';
```

### Retention Policies
```sql
-- Archive old logs
INSERT INTO pipeline_logs_archive
SELECT * FROM pipeline_logs
WHERE created_at < NOW() - INTERVAL '30 days';

-- Clean up old logs
DELETE FROM pipeline_logs
WHERE created_at < NOW() - INTERVAL '30 days';

-- Vacuum to reclaim space
VACUUM ANALYZE pipeline_logs;
```

## Integration with External Tools

### Slack Integration
```python
# src/monitoring/slack_notifier.py
import requests

class SlackNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
    
    def send_notification(self, message, severity='info'):
        colors = {
            'info': '#36a64f',
            'warning': '#ff9900',
            'error': '#ff0000'
        }
        
        payload = {
            'attachments': [{
                'color': colors.get(severity, '#808080'),
                'title': 'FDD Pipeline Alert',
                'text': message,
                'footer': 'FDD Pipeline Monitoring',
                'ts': int(datetime.now().timestamp())
            }]
        }
        
        requests.post(self.webhook_url, json=payload)
```

### PagerDuty Integration
```python
# src/monitoring/pagerduty_notifier.py
from pdpyras import APISession

class PagerDutyNotifier:
    def __init__(self, api_key, service_id):
        self.session = APISession(api_key)
        self.service_id = service_id
    
    def create_incident(self, title, details, urgency='high'):
        incident = {
            'incident': {
                'type': 'incident',
                'title': title,
                'service': {
                    'id': self.service_id,
                    'type': 'service_reference'
                },
                'urgency': urgency,
                'body': {
                    'type': 'incident_body',
                    'details': details
                }
            }
        }
        
        return self.session.post('/incidents', json=incident)
```