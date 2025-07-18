# Deployment Guide

## Overview

This comprehensive guide covers deployment options for the FDD Pipeline, from local development to production environments. The system can be deployed using Docker Compose for development/staging or directly on servers for production use.

## Prerequisites

### System Requirements
- Python 3.11 or higher
- 16GB+ RAM (32GB recommended for GPU processing)
- 100GB+ disk space (15GB for MinerU models + document storage)
- Windows, macOS, or Linux
- NVIDIA GPU with 6GB+ VRAM (optional, for MinerU acceleration)
- Docker 20.10+ and Docker Compose 2.0+ (for containerized deployment)

### Required Software
- Git
- UV package manager (replaces pip)
- PostgreSQL client (for Supabase connection)
- Chrome/Chromium browser (installed via Playwright)

### Access Requirements
- Supabase project with database and storage
- Google Cloud service account with Drive API access
- LLM API keys (Gemini required, OpenAI/Ollama optional)
- Internal API token for secured endpoints

## Quick Start with Docker

The fastest way to get started is using Docker Compose:

```bash
# Clone repository
git clone https://github.com/your-org/fdd-pipeline.git
cd fdd-pipeline

# Copy environment template
cp .env.template .env
# Edit .env with your credentials

# Start all services
docker-compose up -d

# Check health
python scripts/health_check.py

# View logs
docker-compose logs -f
```

Service URLs:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Prefect UI: http://localhost:4200
- pgAdmin: http://localhost:5050 (if enabled)

## Manual Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/your-org/fdd-pipeline.git
cd fdd-pipeline
```

### 2. Set Up Python Environment

```bash
# Install UV if not already installed (using pipx is recommended)
# Option 1: Using pipx (recommended)
pipx install uv

# Option 2: Using pip (if pipx not available)
pip install --user uv

# Option 3: Using curl (standalone installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

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
uv pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install MinerU separately (GPU support)
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# Download MinerU models (one-time, ~15GB)
magic-pdf model-download
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Database Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# Google Drive Configuration
GDRIVE_FOLDER_ID=your-shared-folder-id
GDRIVE_CREDS_JSON=/path/to/service-account-key.json

# LLM API Keys
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-key  # Optional
OLLAMA_BASE_URL=http://localhost:11434  # Optional

# Internal API Security
INTERNAL_API_TOKEN=your-secure-random-token

# Prefect Configuration
PREFECT_API_URL=http://localhost:4200/api
PREFECT_HOME=~/.prefect

# Pipeline Configuration
LOG_LEVEL=INFO
MAX_WORKERS=4
RETRY_ATTEMPTS=3
RETRY_DELAY_SECONDS=60

# MinerU Configuration
MINERU_MODE=local  # or 'api'
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
# Run Supabase migrations
supabase db push

# Or run SQL migrations manually
psql $DATABASE_URL < migrations/001_initial_schema.sql
psql $DATABASE_URL < migrations/002_add_indexes.sql
psql $DATABASE_URL < migrations/003_add_views.sql
psql $DATABASE_URL < migrations/004_add_rls.sql
psql $DATABASE_URL < migrations/005_drive_files_table.sql
psql $DATABASE_URL < migrations/006_vector_similarity_functions.sql
```

### 7. Start Services

```bash
# Start Prefect server
prefect server start

# In another terminal, start the API
python -m src.api.run --reload

# In another terminal, start Prefect agent
prefect agent start -q default
```

### 8. Deploy Prefect Flows

```bash
# Install MinerU with full dependencies using UV
uv pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# Download models (one-time setup, ~15GB)
magic-pdf model-download

# Verify installation
magic-pdf --version

# Test GPU availability (if applicable)
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

```bash
# Deploy flows using Makefile
make prefect-deploy

# Or manually deploy each flow
prefect deployment build flows/scrape_wisconsin.py:scrape_wisconsin -n wi-weekly
prefect deployment build flows/scrape_minnesota.py:scrape_minnesota -n mn-weekly
prefect deployment apply
```

## Production Deployment with Docker

### 1. Build Production Images

```bash
# Build with production optimizations
docker build -t fdd-pipeline:latest .

# Tag for registry
docker tag fdd-pipeline:latest your-registry/fdd-pipeline:latest

# Push to registry
docker push your-registry/fdd-pipeline:latest
```

### 2. Deploy with Docker Compose

```bash
# Production deployment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale workers
docker-compose scale prefect-agent=3
```

### 3. Configure Monitoring

```bash
# Start monitoring service
python scripts/monitoring.py --interval 60

# Or run as Docker service
docker run -d \
  --name fdd-monitoring \
  --env-file .env \
  fdd-pipeline:latest \
  python scripts/monitoring.py
```

## Verification and Testing

### 1. Run Health Check

```bash
# Comprehensive health check
python scripts/health_check.py

# JSON output for automation
python scripts/health_check.py --json
```

### 2. Test Core Functionality

```bash
# Test entity deduplication
python -c "from utils.entity_operations import deduplicate_all_franchises; print(deduplicate_all_franchises())"

# Test API endpoints
curl http://localhost:8000/health
curl -H "Authorization: Bearer $INTERNAL_API_TOKEN" \
  -X POST http://localhost:8000/prefect/run/wi
```

### 3. Manual Flow Execution

```bash
# Trigger Wisconsin scrape
prefect deployment run scrape-wisconsin/wi-weekly

# Trigger Minnesota scrape  
prefect deployment run scrape-minnesota/mn-weekly
```

## Production Checklist

### Pre-Deployment
- [ ] All environment variables configured in `.env`
- [ ] Database migrations applied successfully
- [ ] Google Drive service account has proper permissions
- [ ] LLM API keys validated (especially Gemini)
- [ ] Internal API token generated securely
- [ ] MinerU models downloaded (~15GB)
- [ ] GPU drivers and CUDA installed (if applicable)
- [ ] Docker images built and tested
- [ ] Sufficient disk space (100GB+)

### Deployment
- [ ] All services healthy via health check
- [ ] API responding at `/health` endpoint
- [ ] Prefect UI accessible
- [ ] Flows deployed and visible in UI
- [ ] Test document processed successfully
- [ ] Entity deduplication working

### Post-Deployment
- [ ] Monitoring script running
- [ ] Logs aggregating properly
- [ ] First scheduled runs completed
- [ ] Performance metrics baseline established
- [ ] Backup procedures tested

## Operational Procedures

### Scaling Workers

```bash
# Docker Compose
docker-compose scale prefect-agent=5

# Kubernetes
kubectl scale deployment prefect-agent --replicas=5
```

### Rolling Updates

```bash
# Build new image
docker build -t fdd-pipeline:v2.0 .

# Update one service at a time
docker-compose stop api
docker-compose up -d api

# Verify health before continuing
python scripts/health_check.py
```

### Emergency Rollback

```bash
# Stop all services
docker-compose down

# Revert to previous version
git checkout v1.9
docker-compose up -d

# Restore database if needed
psql $DATABASE_URL < backups/pre-deployment-backup.sql
```

## Performance Tuning

### MinerU Optimization

```bash
# GPU memory optimization
export MINERU_BATCH_SIZE=1  # Reduce for limited VRAM
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# CPU optimization (no GPU)
export MINERU_DEVICE=cpu
export OMP_NUM_THREADS=8  # Match CPU cores
```

### Database Connection Pooling

```python
# In config.py or environment
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
```

### Rate Limiting

```python
# Scraper delays (in seconds)
MINNESOTA_SCRAPER_DELAY=2.0
WISCONSIN_SCRAPER_DELAY=1.5
MAX_CONCURRENT_DOWNLOADS=3
```

## Troubleshooting

### Common Issues

1. **API Not Responding**
   ```bash
   # Check logs
   docker-compose logs api
   # Restart service
   docker-compose restart api
   ```

2. **Prefect Flows Not Running**
   ```bash
   # Check agent logs
   docker-compose logs prefect-agent
   # Verify deployments
   prefect deployment ls
   ```

3. **MinerU GPU Errors**
   ```bash
   # Check CUDA
   nvidia-smi
   # Fallback to CPU
   export MINERU_DEVICE=cpu
   ```

4. **Database Connection Issues**
   ```bash
   # Test connection
   psql $DATABASE_URL -c "SELECT 1"
   # Check Supabase status
   curl https://status.supabase.com
   ```

## Maintenance Scripts

```bash
# Database backup
pg_dump $DATABASE_URL > backup-$(date +%Y%m%d).sql

# Clean old logs
find logs/ -name "*.log" -mtime +30 -delete

# Deduplicate franchises
python -c "from utils.entity_operations import deduplicate_all_franchises; deduplicate_all_franchises()"

# Export metrics
python scripts/monitoring.py --once --json > metrics-$(date +%Y%m%d).json
```

## Additional Resources

- [Architecture Documentation](../01_architecture/system_overview.md)
- [API Reference](../05_api_reference/internal_api.md)
- [Database Schema](../02_data_model/database_schema.md)
- [Troubleshooting Guide](troubleshooting.md)
- [MinerU Integration](../05_api_reference/mineru_integration.md)