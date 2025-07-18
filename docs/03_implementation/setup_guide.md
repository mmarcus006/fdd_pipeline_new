# Setup Guide

This guide walks you through setting up the FDD Pipeline development environment from scratch. By the end, you'll have a fully functional local environment ready for development.

## Prerequisites

### Required Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Python | 3.11+ | Runtime | [python.org](https://python.org) |
| PostgreSQL | 14+ | Database (via Supabase) | Handled by Supabase |
| Git | 2.30+ | Version control | [git-scm.com](https://git-scm.com) |
| UV | Latest | Package management | See installation section below |

### Recommended Software

| Software | Purpose | Installation |
|----------|---------|--------------|
| Docker | Local PostgreSQL testing | [docker.com](https://docker.com) |
| VS Code | IDE with Python support | [code.visualstudio.com](https://code.visualstudio.com) |
| Postman | API testing | [postman.com](https://postman.com) |

### System Requirements

- **RAM**: Minimum 8GB, recommended 16GB (32GB for GPU processing)
- **Storage**: 65GB free space (50GB for documents + 15GB for MinerU models)
- **Network**: Stable internet for API calls and model downloads
- **GPU**: CUDA-capable GPU recommended (GTX 1060 or better)

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
# Option 1: Install UV using pipx (recommended)
pipx install uv

# Option 2: Using the standalone installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Option 3: Using pip (if other options unavailable)
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
# Install all dependencies from lock file (if exists)
uv pip sync requirements.txt

# Or install from pyproject.toml (recommended)
uv pip install -e ".[dev]"

# UV automatically handles dependency resolution
# No need for separate requirements-dev.txt
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

### 3.3 MinerU Local Setup

#### Prerequisites
- **GPU Requirements** (Recommended):
  - NVIDIA GPU with Turing architecture or newer (GTX 1060+ with 6GB+ VRAM)
  - CUDA 11.8+ installed and configured
  - NVIDIA drivers version 520+ 
- **Storage**: 20GB+ free space (15GB for models + 5GB for processing)
- **RAM**: 16GB minimum, 32GB recommended

#### Step 1: Verify GPU Availability (Optional but Recommended)
```bash
# Check NVIDIA GPU
nvidia-smi

# Verify CUDA installation
nvcc --version

# Test PyTorch CUDA support
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'CUDA device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"No GPU\"}')"
```

#### Step 2: Install MinerU
```bash
# Install with GPU support using UV (recommended)
uv pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# Or install with pip if UV fails
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com

# For CPU-only version (10-50x slower, use only if no GPU)
uv pip install magic-pdf

# Optional: Install PaddlePaddle for enhanced OCR (GPU version)
pip install paddlepaddle-gpu==3.0.0b1 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

#### Step 3: Download Models
```bash
# Download all required models (~15GB, takes 15-30 minutes)
magic-pdf model-download

# Models will be saved to ~/.mineru/models
# You should see these directories after download:
ls ~/.mineru/models/
# Expected output:
# Layout/  MFD/  MFR/  OCR/

# Verify model sizes
du -sh ~/.mineru/models/*
# Expected sizes:
# 2.5G    Layout/
# 3.2G    MFD/
# 4.8G    MFR/
# 4.5G    OCR/
```

#### Step 4: Configure MinerU
```bash
# Create configuration file
cat > ~/magic-pdf.json << 'EOF'
{
    "models-dir": "~/.mineru/models",
    "device-mode": "cuda",
    "layout-config": {
        "model": "doclayout_yolo"
    },
    "formula-config": {
        "mfd_model": "yolo_v8_mfd",
        "mfr_model": "unimernet_small",
        "enable": true
    },
    "table-config": {
        "model": "rapid_table",
        "enable": true,
        "max_time": 400
    }
}
EOF

# For CPU-only mode, change device-mode to "cpu"
```

#### Step 5: Set Environment Variables
```bash
# Add to your .env file
echo "# MinerU Local Configuration" >> .env
echo "MINERU_MODEL_PATH=~/.mineru/models" >> .env
echo "MINERU_DEVICE=cuda  # or 'cpu' if no GPU" >> .env
echo "MINERU_BATCH_SIZE=2  # Reduce to 1 if GPU memory errors" >> .env
echo "MINERU_MAX_PAGES=500  # Maximum pages per document" >> .env
```

#### Step 6: Verify Installation
```bash
# Check version
magic-pdf --version
# Expected: magic-pdf 1.3.12 or higher

# Test basic functionality
wget https://arxiv.org/pdf/2308.00352.pdf -O test.pdf
magic-pdf pdf-command --pdf test.pdf --output-dir test_output/

# Check output
ls test_output/
# Should see: images/ layout.json output.md

# Test with Python API
python << 'EOF'
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
import os

# Test configuration
print("Testing MinerU Python API...")

# Create output directory
os.makedirs("test_api_output", exist_ok=True)
image_writer = DiskReaderWriter("test_api_output")

# Read test PDF
with open("test.pdf", "rb") as f:
    pdf_bytes = f.read()

# Process
try:
    pipe = UNIPipe(pdf_bytes, {"_pdf_type": "", "model_list": []}, image_writer)
    pipe.pipe_classify()
    if hasattr(pipe, 'pipe_analyze'):
        pipe.pipe_analyze()
    pipe.pipe_parse()
    
    print("✓ MinerU Python API working correctly")
    print(f"✓ Using device: {os.getenv('MINERU_DEVICE', 'cuda')}")
except Exception as e:
    print(f"✗ Error: {e}")
EOF
```

#### Step 7: Performance Testing
```bash
# Create performance test script
cat > test_mineru_performance.py << 'EOF'
import time
import os
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

def test_performance(pdf_path):
    print(f"Testing MinerU performance on: {pdf_path}")
    print(f"Device: {os.getenv('MINERU_DEVICE', 'cuda')}")
    print(f"Batch size: {os.getenv('MINERU_BATCH_SIZE', '2')}")
    
    start = time.time()
    
    # Setup
    image_writer = DiskReaderWriter("perf_test_output")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    # Process
    pipe = UNIPipe(pdf_bytes, {"_pdf_type": "", "model_list": []}, image_writer)
    pipe.pipe_classify()
    if hasattr(pipe, 'pipe_analyze'):
        pipe.pipe_analyze()
    pipe.pipe_parse()
    
    end = time.time()
    
    # Report
    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    processing_time = end - start
    
    print(f"\nResults:")
    print(f"File size: {file_size_mb:.2f} MB")
    print(f"Processing time: {processing_time:.2f} seconds")
    print(f"Speed: {file_size_mb/processing_time:.2f} MB/s")

if __name__ == "__main__":
    test_performance("test.pdf")
EOF

python test_mineru_performance.py
```

#### Troubleshooting Common Installation Issues

**Issue: CUDA/GPU not detected**
```bash
# Solution 1: Set CUDA path explicitly
export CUDA_HOME=/usr/local/cuda
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Solution 2: Use CPU mode
export MINERU_DEVICE=cpu
```

**Issue: Model download fails**
```bash
# Solution: Download models manually
mkdir -p ~/.mineru/models
cd ~/.mineru/models

# Download from Hugging Face mirror (if main site is slow)
git clone https://huggingface.co/opendatalab/mineru-models .
```

**Issue: Out of GPU memory**
```bash
# Solution: Reduce batch size
export MINERU_BATCH_SIZE=1

# Or use memory fraction setting
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
```

**Issue: Import errors**
```bash
# Solution: Reinstall with clean environment
uv pip uninstall magic-pdf mineru -y
uv pip cache purge
uv pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com
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

# MinerU Local
MINERU_MODEL_PATH=~/.mineru/models
MINERU_DEVICE=cuda  # or 'cpu' if no GPU
MINERU_BATCH_SIZE=2  # Adjust based on GPU memory

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
✓ MinerU models loaded
✓ CUDA device available (or CPU mode)
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
# Pre-commit is already installed via UV in dev dependencies
# Just activate the hooks
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
# Solution 1: If installed with pipx, ensure pipx is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Solution 2: If using standalone installer
export PATH="$HOME/.cargo/bin:$PATH"

# Add the appropriate line to ~/.bashrc or ~/.zshrc

# Solution 3: Use UV's built-in shell integration
uv generate-shell-completion bash >> ~/.bashrc  # or zsh/fish
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

### Issue: MinerU GPU not detected
```bash
# Check GPU availability
nvidia-smi  # For NVIDIA GPUs

# Verify CUDA installation
python -c "import torch; print(torch.cuda.is_available())"

# Fallback to CPU mode
export MINERU_DEVICE=cpu
```

### Issue: MinerU models not loading
```bash
# Check model directory
ls ~/.mineru/models

# Re-download if missing
magic-pdf model-download

# Verify disk space
df -h ~/.mineru
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
uv pip sync requirements.txt  # Install from lock file
uv pip install -e .        # Install project in editable mode

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