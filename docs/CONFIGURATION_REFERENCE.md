# Configuration Reference

## Overview

The FDD Pipeline uses environment variables for configuration. This document provides a comprehensive reference for all configuration options.

## Configuration Files

### `.env` File

Create a `.env` file in the project root with your configuration:

```bash
cp .env.example .env
# Edit .env with your settings
```

### `config.py`

The main configuration module that loads and validates settings using Pydantic.

## Environment Variables

### Database Configuration

#### `SUPABASE_URL` (required)
- **Description**: Your Supabase project URL
- **Example**: `https://xyzcompany.supabase.co`
- **Usage**: Database connections and API calls

#### `SUPABASE_ANON_KEY` (required)
- **Description**: Supabase anonymous/public key
- **Example**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
- **Usage**: Public API access

#### `SUPABASE_SERVICE_KEY` (required)
- **Description**: Supabase service role key (bypasses RLS)
- **Example**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
- **Usage**: Administrative database operations
- **Security**: Keep secret, never expose in client code

### LLM API Configuration

#### `GEMINI_API_KEY` (required)
- **Description**: Google Gemini API key
- **Example**: `AIzaSyD-xxxxxxxxxxxxxx`
- **Usage**: Primary LLM for complex extractions
- **Get it from**: https://makersuite.google.com/app/apikey

#### `OPENAI_API_KEY` (optional)
- **Description**: OpenAI API key
- **Example**: `sk-xxxxxxxxxxxxxxxx`
- **Usage**: Fallback LLM for high-accuracy tasks
- **Get it from**: https://platform.openai.com/api-keys

#### `OLLAMA_BASE_URL` (optional)
- **Description**: Ollama server URL
- **Default**: `http://localhost:11434`
- **Usage**: Local LLM inference
- **Setup**: Install Ollama and pull models

### Google Drive Configuration

#### `GDRIVE_CREDS_JSON` (required)
- **Description**: Path to Google service account credentials
- **Default**: `gdrive_cred.json`
- **Example**: `/path/to/service-account-key.json`
- **Usage**: Google Drive API authentication

#### `GDRIVE_FOLDER_ID` (required)
- **Description**: Root folder ID in Google Drive
- **Example**: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs`
- **Usage**: Where to store FDD documents
- **How to find**: Right-click folder → Get link → Extract ID

### MinerU Configuration

#### `MINERU_AUTH_FILE` (optional)
- **Description**: Path to store MinerU authentication
- **Default**: `mineru_auth.json`
- **Usage**: Caches browser authentication

### Section Detection Configuration

#### `USE_ENHANCED_SECTION_DETECTION` (optional)
- **Description**: Enable Claude-powered section detection
- **Default**: `true`
- **Values**: `true`, `false`
- **Usage**: More accurate section boundary detection

#### `ENHANCED_DETECTION_CONFIDENCE_THRESHOLD` (optional)
- **Description**: Minimum confidence for section detection
- **Default**: `0.7`
- **Range**: `0.0` to `1.0`
- **Usage**: Higher = more accurate but may miss sections

#### `ENHANCED_DETECTION_MIN_FUZZY_SCORE` (optional)
- **Description**: Minimum fuzzy match score for headers
- **Default**: `80`
- **Range**: `0` to `100`
- **Usage**: Lower = more lenient matching

### Application Settings

#### `DEBUG` (optional)
- **Description**: Enable debug mode
- **Default**: `false`
- **Values**: `true`, `false`
- **Usage**: Verbose logging and error details

#### `LOG_LEVEL` (optional)
- **Description**: Logging verbosity
- **Default**: `INFO`
- **Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Usage**: Control log output

#### `MAX_CONCURRENT_EXTRACTIONS` (optional)
- **Description**: Maximum parallel LLM extractions
- **Default**: `5`
- **Range**: `1` to `10`
- **Usage**: Prevent rate limiting

## Configuration Examples

### Minimal Configuration

```bash
# .env
SUPABASE_URL=https://xyzcompany.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
GEMINI_API_KEY=AIzaSyD-xxxxxxxxxxxxxx
GDRIVE_FOLDER_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs
```

### Development Configuration

```bash
# .env.development
DEBUG=true
LOG_LEVEL=DEBUG
MAX_CONCURRENT_EXTRACTIONS=2

# Use local Ollama for cost savings
OLLAMA_BASE_URL=http://localhost:11434

# Lower thresholds for testing
ENHANCED_DETECTION_CONFIDENCE_THRESHOLD=0.5
ENHANCED_DETECTION_MIN_FUZZY_SCORE=60
```

### Production Configuration

```bash
# .env.production
DEBUG=false
LOG_LEVEL=WARNING
MAX_CONCURRENT_EXTRACTIONS=10

# High accuracy settings
ENHANCED_DETECTION_CONFIDENCE_THRESHOLD=0.8
ENHANCED_DETECTION_MIN_FUZZY_SCORE=90

# Include OpenAI for fallback
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
```

## Service Account Setup

### Google Drive Service Account

1. Create a service account in Google Cloud Console
2. Download the JSON key file
3. Share your Google Drive folder with the service account email
4. Set `GDRIVE_CREDS_JSON` to the path of the JSON file

Example service account JSON:
```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "xxxxx",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "fdd-pipeline@your-project.iam.gserviceaccount.com",
  "client_id": "xxxxx",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

## Validation

The configuration is validated on startup. Common validation errors:

### Missing Required Variables
```
ValueError: SUPABASE_URL is required
```
**Solution**: Add the missing variable to `.env`

### Invalid URL Format
```
ValueError: Invalid Supabase URL format
```
**Solution**: Ensure URL starts with `https://` and ends with `.supabase.co`

### File Not Found
```
FileNotFoundError: gdrive_cred.json not found
```
**Solution**: Check file path and permissions

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use `.env.example`** as a template without real values
3. **Rotate API keys** regularly
4. **Use different keys** for development and production
5. **Restrict service key access** to backend only
6. **Set minimal permissions** on service accounts

## Environment-Specific Settings

### Local Development
```bash
# Use local paths
GDRIVE_CREDS_JSON=./credentials/gdrive_cred.json
MINERU_AUTH_FILE=./auth/mineru_auth.json

# Enable all debugging
DEBUG=true
LOG_LEVEL=DEBUG
```

### Docker Container
```bash
# Use container paths
GDRIVE_CREDS_JSON=/app/credentials/gdrive_cred.json
MINERU_AUTH_FILE=/app/auth/mineru_auth.json

# Production settings
DEBUG=false
LOG_LEVEL=INFO
```

### CI/CD Pipeline
```bash
# Use secrets management
SUPABASE_URL=${SUPABASE_URL_SECRET}
SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY_SECRET}
GEMINI_API_KEY=${GEMINI_API_KEY_SECRET}
```

## Troubleshooting

### Check Current Configuration

```python
from config import get_settings

settings = get_settings()
print(f"Supabase URL: {settings.supabase_url}")
print(f"Debug mode: {settings.debug}")
print(f"Log level: {settings.log_level}")
```

### Verify Environment Loading

```bash
# Check if .env is loaded
python -c "import os; print(os.getenv('SUPABASE_URL', 'NOT SET'))"
```

### Common Issues

1. **Variables not loading**
   - Check `.env` file location (must be in project root)
   - Ensure no spaces around `=` in `.env`
   - Verify file encoding is UTF-8

2. **Authentication failures**
   - Regenerate API keys
   - Check key permissions/scopes
   - Verify service account has necessary access

3. **Path issues**
   - Use absolute paths for file references
   - Check file permissions
   - Ensure directories exist

## Advanced Configuration

### Custom Settings Class

Extend the base settings for custom needs:

```python
from config import Settings

class CustomSettings(Settings):
    # Add custom fields
    custom_api_url: str = "https://api.example.com"
    feature_flag_x: bool = False
    
    class Config:
        env_prefix = "FDD_"  # Use FDD_CUSTOM_API_URL
```

### Dynamic Configuration

Load configuration based on environment:

```python
import os
from pathlib import Path

env = os.getenv("ENVIRONMENT", "development")
env_file = Path(f".env.{env}")

if env_file.exists():
    os.environ["ENV_FILE"] = str(env_file)
```

### Configuration Validation

Add custom validation:

```python
from pydantic import validator

class Settings(BaseSettings):
    gemini_api_key: str
    
    @validator("gemini_api_key")
    def validate_api_key(cls, v):
        if not v.startswith("AIza"):
            raise ValueError("Invalid Gemini API key format")
        return v
```