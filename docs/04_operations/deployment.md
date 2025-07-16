# Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the FDD Pipeline in a local Prefect environment. The pipeline scrapes Franchise Disclosure Documents (FDDs) from Minnesota and Wisconsin regulatory portals on a weekly schedule.

## Prerequisites

### System Requirements
- Python 3.11 or higher
- 8GB+ RAM available (16GB+ recommended for MinerU)
- 25GB+ disk space (10GB for data/logs + 15GB for MinerU models)
- Windows, macOS, or Linux
- CUDA-capable GPU (optional but recommended for MinerU)

### Required Software
- Git
- Python with pip
- PostgreSQL client (for Supabase connection)
- Chrome/Chromium browser (for Selenium)

### Access Requirements
- Supabase project credentials
- Google Cloud service account with Drive API access
- SMTP server credentials for email notifications
- Network access to university websites

## Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/your-org/fdd_pipeline_new.git
cd fdd_pipeline_new
```

### 2. Set Up Python Environment

```bash
# Install UV if not already installed
pip install uv

# Create virtual environment with UV
uv venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
# Install production dependencies with UV
uv pip sync requirements.txt

# Or install from pyproject.toml
uv pip install -e .
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# Google Drive Configuration
GDRIVE_FOLDER_ID=your-shared-folder-id
GDRIVE_CREDS_JSON=/path/to/service-account-key.json

# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL_TO=alerts@your-org.com
ALERT_EMAIL_FROM=fdd-pipeline@your-org.com

# Prefect Configuration
PREFECT_API_URL=http://localhost:4200/api
PREFECT_HOME=~/.prefect

# Pipeline Configuration
LOG_LEVEL=INFO
MAX_WORKERS=4
RETRY_ATTEMPTS=3
RETRY_DELAY_SECONDS=60

# MinerU Local Configuration
MINERU_MODEL_PATH=~/.mineru/models
MINERU_DEVICE=cuda  # or 'cpu' if no GPU
MINERU_BATCH_SIZE=2  # Adjust based on GPU memory
```

### 5. Set Up Google Service Account

1. Place your Google service account JSON file in `config/`:
   ```bash
   mkdir -p config
   cp /path/to/service-account.json config/google-service-account.json
   ```

2. Ensure the service account has Editor access to the target Google Drive folder

### 6. Initialize Database Schema

```bash
# Run database migrations
python scripts/init_database.py

# Verify tables created
python scripts/verify_database.py
```

### 7. Install ChromeDriver

```bash
# Windows
python scripts/install_chromedriver.py

# macOS (using Homebrew)
brew install chromedriver

# Linux
sudo apt-get update
sudo apt-get install chromium-chromedriver
```

### 8. Install MinerU Local

```bash
# Install MinerU with full dependencies
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# Download models (one-time setup, ~15GB)
magic-pdf model-download

# Verify installation
magic-pdf --version

# Test GPU availability (if applicable)
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

## Prefect Deployment

### 1. Start Prefect Server

```bash
# Initialize Prefect database
prefect server database reset -y

# Start Prefect server
prefect server start
```

The Prefect UI will be available at http://localhost:4200

### 2. Create Work Pool

```bash
# Create local process work pool
prefect work-pool create fdd-local-pool --type process
```

### 3. Deploy Flows

```bash
# Deploy Minnesota flow
python deployments/deploy_mn_flow.py

# Deploy Wisconsin flow
python deployments/deploy_wi_flow.py

# Deploy maintenance flow
python deployments/deploy_maintenance_flow.py
```

### 4. Create Schedules

```bash
# Schedule Minnesota scrape (Mondays 2am)
prefect deployment schedule create minnesota-scrape/prod \
  --cron "0 2 * * 1" \
  --timezone "America/Chicago"

# Schedule Wisconsin scrape (Mondays 3am)
prefect deployment schedule create wisconsin-scrape/prod \
  --cron "0 3 * * 1" \
  --timezone "America/Chicago"

# Schedule Google Drive cleanup (Daily 1am)
prefect deployment schedule create drive-cleanup/prod \
  --cron "0 1 * * *" \
  --timezone "America/Chicago"
```

### 5. Start Worker

```bash
# Start worker for the local pool
prefect worker start --pool fdd-local-pool
```

## Verification Steps

### 1. Test Database Connection

```bash
python -c "from src.utils.database import test_connection; test_connection()"
```

### 2. Test Email Notifications

```bash
python scripts/test_email.py
```

### 3. Run Test Scrape

```bash
# Test single department
python scripts/test_scrape.py --university mn --department "Computer Science"
```

### 4. Verify Prefect Deployment

```bash
# List deployments
prefect deployment ls

# Run deployment manually
prefect deployment run minnesota-scrape/prod
```

## Production Checklist

### Pre-Deployment
- [ ] All environment variables configured
- [ ] Database schema initialized
- [ ] Google Drive permissions verified
- [ ] Email notifications tested
- [ ] ChromeDriver installed and accessible
- [ ] MinerU models downloaded (~15GB)
- [ ] GPU drivers installed (if using CUDA)
- [ ] Sufficient disk space available (25GB+)

### Deployment
- [ ] Prefect server running
- [ ] Work pools created
- [ ] Flows deployed successfully
- [ ] Schedules configured
- [ ] Workers started
- [ ] Initial test run completed

### Post-Deployment
- [ ] Monitoring dashboards accessible
- [ ] Log aggregation working
- [ ] Email alerts functional
- [ ] First scheduled run successful
- [ ] Performance baselines established

## Rollback Procedures

### Quick Rollback

1. Stop workers:
   ```bash
   # Find worker process
   ps aux | grep "prefect worker"
   # Kill worker process
   kill -TERM <worker-pid>
   ```

2. Pause deployments:
   ```bash
   prefect deployment pause minnesota-scrape/prod
   prefect deployment pause wisconsin-scrape/prod
   ```

3. Revert code:
   ```bash
   git checkout <previous-version-tag>
   pip install -r requirements.txt
   ```

4. Restart services:
   ```bash
   prefect worker start --pool fdd-local-pool
   prefect deployment resume minnesota-scrape/prod
   prefect deployment resume wisconsin-scrape/prod
   ```

## Security Considerations

### Credentials Management
- Never commit credentials to version control
- Use environment variables or secure vaults
- Rotate credentials regularly
- Limit service account permissions

### Network Security
- Run behind corporate firewall
- Use HTTPS for all external connections
- Implement rate limiting for scraping
- Monitor for unusual activity

### Data Protection
- Encrypt sensitive data at rest
- Use secure connections to Supabase
- Implement data retention policies
- Regular security audits

## Maintenance Windows

### Scheduled Maintenance
- Tuesdays 10pm-12am CT (low activity period)
- Notify stakeholders 48 hours in advance
- Have rollback plan ready
- Test in staging first

### Emergency Maintenance
- Follow incident response procedures
- Notify on-call team immediately
- Document all changes
- Post-mortem within 48 hours

## Support

### Internal Resources
- Team Slack: #fdd-pipeline-support
- Wiki: https://wiki.internal/fdd-pipeline
- On-call rotation: See PagerDuty

### External Resources
- Prefect Docs: https://docs.prefect.io
- Supabase Docs: https://supabase.com/docs
- Project Repository: https://github.com/your-org/fdd_pipeline_new