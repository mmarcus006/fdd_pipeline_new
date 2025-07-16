# Setup Guide

This guide walks you through setting up the FDD Pipeline development environment from scratch. By the end, you'll have a fully functional local environment ready for development.

## Prerequisites

### Required Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Python | 3.11+ | Runtime | [python.org](https://python.org) |
| PostgreSQL | 14+ | Database (via Supabase) | Handled by Supabase |
| Git | 2.30+ | Version control | [git-scm.com](https://git-scm.com) |
| UV | Latest | Package management | `pip install uv` |

### Recommended Software

| Software | Purpose | Installation |
|----------|---------|--------------|
| Docker | Local PostgreSQL testing | [docker.com](https://docker.com) |
| VS Code | IDE with Python support | [code.visualstudio.com](https://code.visualstudio.com) |
| Postman | API testing | [postman.com](https://postman.com) |

### System Requirements

- **RAM**: Minimum 8GB, recommended 16GB
- **Storage**: 50GB free space for documents and models
- **Network**: Stable internet for API calls

## Step 1: Clone Repository

```bash
# Clone the repository
git clone https://github.com/yourorg/fdd-pipeline.git
cd fdd-pipeline

# Create a new branch for your work
git checkout -b feature/your-feature-name
```

## Step 2: Python Environment Setup

### Install UV

```bash
# Install UV globally
pip install --user uv

# Verify installation
uv --version
```

### Create Virtual Environment

```bash
# UV automatically creates .venv
uv venv

# Activate the environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

### Install Dependencies

```bash
# Install all dependencies
uv pip sync requirements.txt

# Install development dependencies
uv pip install -r requirements-dev.txt

# Or install from pyproject.toml
uv pip install -e ".[dev]"
```

## Step 3: External Services Setup

### 3.1 Supabase Setup

1. **Create Supabase Project**
   - Go to [supabase.com](https://supabase.com)
   - Create new project
   - Save the project URL and keys

2. **Run Database Migrations**
   ```bash
   # Install Supabase CLI
   npm install -g supabase
   
   # Login to Supabase
   supabase login
   
   # Link to your project
   supabase link --project-ref your-project-ref
   
   # Run migrations
   supabase db push
   ```

3. **Verify Tables**
   - Open Supabase dashboard
   - Check Tables tab for all schema objects

### 3.2 Google Cloud Setup

1. **Create Service Account**
   ```bash
   # Using gcloud CLI (optional)
   gcloud iam service-accounts create fdd-pipeline \
     --display-name="FDD Pipeline Service"
   ```

2. **Via Console**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Navigate to IAM & Admin > Service Accounts
   - Create new service account
   - Download JSON key file

3. **Google Drive Setup**
   - Create a folder in Google Drive for FDD storage
   - Share folder with service account email
   - Note the folder ID from URL

### 3.3 MinerU API Setup

1. **Get API Access**
   - Register at MinerU platform
   - Generate API key
   - Note endpoint URL

2. **Test Connection**
   ```python
   import httpx
   
   response = httpx.get(
       "https://api.mineru.com/v1/status",
       headers={"Authorization": f"Bearer {MINERU_API_KEY}"}
   )
   print(response.json())
   ```

### 3.4 LLM Providers Setup

#### Gemini Pro
1. Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Enable Gemini API in Google Cloud Console

#### OpenAI (Fallback)
1. Get API key from [OpenAI Platform](https://platform.openai.com)
2. Add billing information

#### Ollama (Local)
1. **Install Ollama**
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Windows
   # Download from https://ollama.ai/download
   ```

2. **Pull Required Models**
   ```bash
   ollama pull phi3:mini
   ollama pull llama3:8b-instruct
   ```

3. **Verify Installation**
   ```bash
   ollama list
   ```

## Step 4: Environment Configuration

### Create .env File

```bash
# Copy template
cp .env.template .env
```

### Configure Environment Variables

Edit `.env` with your values:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Google Drive Configuration
GDRIVE_CREDS_JSON=/path/to/service-account-key.json
GDRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j

# MinerU API
MINERU_API_KEY=mk_1234567890abcdef
MINERU_BASE_URL=https://api.mineru.com/v1

# LLM Providers
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434

# Email Configuration (for alerts)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-specific-password
ALERT_RECIPIENTS=team@yourcompany.com

# Prefect Configuration
PREFECT_API_URL=http://localhost:4200/api
PREFECT_API_KEY=local-dev-key
```

### Validate Configuration

```python
# Run configuration check
python scripts/check_config.py
```

Expected output:
```
✓ Supabase connection successful
✓ Google Drive authenticated
✓ MinerU API accessible
✓ Gemini API validated
✓ Ollama server running
✓ SMTP configuration valid
```

## Step 5: Prefect Setup

### Start Prefect Server

```bash
# Terminal 1: Start Prefect server
prefect server start
```

Navigate to http://localhost:4200 to access Prefect UI.

### Create Work Pool

```bash
# Terminal 2: Create local work pool
prefect work-pool create --type process local-pool
```

### Deploy Flows

```bash
# Build deployments
prefect deployment build flows/scrape_mn.py:scrape_minnesota \
  -n mn-weekly \
  -p local-pool \
  --cron "0 2 * * 1"  # Weekly on Monday at 2 AM

prefect deployment build flows/scrape_wi.py:scrape_wisconsin \
  -n wi-weekly \
  -p local-pool \
  --cron "0 3 * * 1"  # Weekly on Monday at 3 AM

# Apply deployments
prefect deployment apply scrape_minnesota-deployment.yaml
prefect deployment apply scrape_wisconsin-deployment.yaml
```

### Start Agent

```bash
# Terminal 3: Start Prefect agent
prefect agent start -p local-pool
```

## Step 6: Development Tools Setup

### Install Pre-commit Hooks

```bash
# Install pre-commit
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

### Configure IDE

#### VS Code Settings

Create `.vscode/settings.json`:

```json
{
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.linting.mypyEnabled": true,
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests"
    ]
}
```

#### VS Code Extensions

Install recommended extensions:
- Python
- Pylance
- Black Formatter
- GitLens
- Thunder Client (API testing)

## Step 7: Verify Installation

### Run Test Suite

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_scrapers.py
```

### Test Manual Flow Run

```python
# Test scraper
python -m flows.scrape_mn --limit 5

# Test extraction
python scripts/test_extraction.py sample_data/test_fdd.pdf
```

### Check Database Connection

```python
from src.database import get_supabase_client

client = get_supabase_client()
result = client.table('franchisors').select('*').limit(5).execute()
print(f"Found {len(result.data)} franchisors")
```

## Step 8: Common Setup Issues

### Issue: UV command not found
```bash
# Solution: Add to PATH
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.bashrc or ~/.zshrc
```

### Issue: Supabase connection timeout
```bash
# Check firewall/VPN
# Verify SUPABASE_URL includes https://
# Test with curl:
curl https://your-project.supabase.co/rest/v1/
```

### Issue: Google Drive authentication fails
```python
# Verify service account has access
# Check JSON key file path is absolute
# Test with simple script:
from google.oauth2 import service_account
creds = service_account.Credentials.from_service_account_file(
    '/path/to/key.json'
)
print("Auth successful")
```

### Issue: Ollama models not loading
```bash
# Ensure Ollama service is running
ollama serve

# Check model is downloaded
ollama list

# Test model
ollama run phi3:mini "Hello"
```

## Step 9: Next Steps

1. **Run a test scrape**
   ```bash
   prefect deployment run scrape-minnesota/mn-weekly --limit 10
   ```

2. **Monitor in Prefect UI**
   - Check flow runs at http://localhost:4200
   - View logs and task states

3. **Review extracted data**
   - Check Supabase dashboard
   - Query via SQL editor

4. **Read development workflow**
   - See [Development Workflow](development_workflow.md)
   - Review coding standards

## Useful Commands Reference

```bash
# Environment
uv venv                    # Create virtual environment
source .venv/bin/activate  # Activate (Linux/macOS)
.venv\Scripts\activate     # Activate (Windows)
uv pip sync               # Install dependencies

# Prefect
prefect server start      # Start server
prefect agent start       # Start agent
prefect deployment run    # Trigger flow

# Development
black .                   # Format code
flake8                    # Lint code
mypy .                    # Type check
pytest                    # Run tests
pre-commit run           # Run all checks

# Database
supabase db push         # Run migrations
supabase db reset        # Reset database
```

## Getting Help

- **Documentation**: Check `/docs` folder
- **Issues**: File on GitHub
- **Team Chat**: Join Slack channel #fdd-pipeline
- **Email**: fdd-support@yourcompany.com

---

Congratulations! Your FDD Pipeline development environment is now ready. Start by running a test scrape to ensure everything is working correctly.