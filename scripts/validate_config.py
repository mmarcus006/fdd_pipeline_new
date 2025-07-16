#!/usr/bin/env python
"""
Configuration Validation Script

Validates all configuration settings and environment variables.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings, Settings
from utils.logging import get_logger

logger = get_logger("config_validator")


class ConfigValidator:
    """Validate FDD Pipeline configuration."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        
    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("\n" + "=" * 60)
        print("FDD PIPELINE CONFIGURATION VALIDATION")
        print("=" * 60)
        
        # Try to load settings
        try:
            settings = get_settings()
            self.info.append("✅ Configuration loaded successfully")
        except Exception as e:
            self.errors.append(f"❌ Failed to load configuration: {e}")
            return False
        
        # Validate environment variables
        self.validate_environment()
        
        # Validate database settings
        self.validate_database(settings)
        
        # Validate Google Drive settings
        self.validate_google_drive(settings)
        
        # Validate LLM API settings
        self.validate_llm_apis(settings)
        
        # Validate MinerU settings
        self.validate_mineru(settings)
        
        # Validate file paths
        self.validate_paths(settings)
        
        # Validate Prefect settings
        self.validate_prefect(settings)
        
        # Print results
        self.print_results()
        
        return len(self.errors) == 0
    
    def validate_environment(self):
        """Check for .env file."""
        env_file = Path(".env")
        if env_file.exists():
            self.info.append("✅ .env file found")
        else:
            env_template = Path(".env.template")
            if env_template.exists():
                self.warnings.append("⚠️  No .env file found - copy .env.template and configure")
            else:
                self.errors.append("❌ No .env or .env.template file found")
    
    def validate_database(self, settings: Settings):
        """Validate database configuration."""
        if settings.supabase_url and settings.supabase_anon_key:
            self.info.append("✅ Supabase credentials configured")
            
            # Check if URL is valid format
            if not settings.supabase_url.startswith("https://"):
                self.warnings.append("⚠️  Supabase URL should start with https://")
                
            # Check service key
            if settings.supabase_service_key:
                self.info.append("✅ Supabase service key configured")
            else:
                self.warnings.append("⚠️  No Supabase service key - some operations may fail")
        else:
            self.errors.append("❌ Missing Supabase credentials")
    
    def validate_google_drive(self, settings: Settings):
        """Validate Google Drive configuration."""
        if settings.gdrive_folder_id:
            self.info.append("✅ Google Drive folder ID configured")
        else:
            self.errors.append("❌ Missing Google Drive folder ID")
        
        if settings.gdrive_creds_json:
            creds_path = Path(settings.gdrive_creds_json)
            if creds_path.exists():
                self.info.append(f"✅ Google Drive credentials file exists: {creds_path}")
            else:
                self.errors.append(f"❌ Google Drive credentials file not found: {creds_path}")
        else:
            self.errors.append("❌ Missing Google Drive credentials path")
    
    def validate_llm_apis(self, settings: Settings):
        """Validate LLM API configurations."""
        # Gemini (required)
        if settings.gemini_api_key:
            self.info.append("✅ Gemini API key configured")
        else:
            self.errors.append("❌ Missing Gemini API key (required)")
        
        # OpenAI (optional)
        if settings.openai_api_key:
            self.info.append("✅ OpenAI API key configured")
        else:
            self.info.append("ℹ️  OpenAI API key not configured (optional)")
        
        # Ollama (optional)
        if settings.ollama_base_url:
            self.info.append(f"✅ Ollama base URL configured: {settings.ollama_base_url}")
            
            # Check if Ollama is running
            try:
                import httpx
                response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
                if response.status_code == 200:
                    self.info.append("✅ Ollama server is reachable")
                else:
                    self.warnings.append("⚠️  Ollama server not responding")
            except Exception:
                self.warnings.append("⚠️  Cannot connect to Ollama server")
        else:
            self.info.append("ℹ️  Ollama not configured (optional)")
    
    def validate_mineru(self, settings: Settings):
        """Validate MinerU configuration."""
        if settings.mineru_mode == "local":
            self.info.append("✅ MinerU configured for local mode")
            
            # Check if MinerU is installed
            try:
                import magic_pdf
                self.info.append("✅ MinerU (magic-pdf) is installed")
            except ImportError:
                self.errors.append("❌ MinerU not installed - run: pip install magic-pdf[full]")
            
            # Check model path
            model_path = Path(settings.mineru_model_path).expanduser()
            if model_path.exists():
                # Check if models are downloaded
                model_files = list(model_path.glob("**/*.pth")) + list(model_path.glob("**/*.onnx"))
                if model_files:
                    self.info.append(f"✅ MinerU models found: {len(model_files)} files")
                else:
                    self.warnings.append("⚠️  No model files found - run: magic-pdf model-download")
            else:
                self.warnings.append(f"⚠️  MinerU model path does not exist: {model_path}")
            
            # Check device setting
            if settings.mineru_device == "cuda":
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.info.append(f"✅ CUDA available for GPU processing")
                    else:
                        self.warnings.append("⚠️  CUDA not available - will fall back to CPU")
                except ImportError:
                    self.warnings.append("⚠️  PyTorch not installed - GPU detection unavailable")
                    
        elif settings.mineru_mode == "api":
            self.info.append("✅ MinerU configured for API mode")
            
            if settings.mineru_api_key:
                self.info.append("✅ MinerU API key configured")
            else:
                self.errors.append("❌ Missing MinerU API key for API mode")
                
            if settings.mineru_base_url:
                self.info.append(f"✅ MinerU API URL: {settings.mineru_base_url}")
            else:
                self.warnings.append("⚠️  Using default MinerU API URL")
    
    def validate_paths(self, settings: Settings):
        """Validate required paths exist."""
        # Check log directory
        log_dir = Path("logs")
        if log_dir.exists():
            self.info.append("✅ Log directory exists")
        else:
            log_dir.mkdir(exist_ok=True)
            self.info.append("✅ Created log directory")
        
        # Check temp directory
        temp_dir = Path("temp")
        if not temp_dir.exists():
            temp_dir.mkdir(exist_ok=True)
            self.info.append("✅ Created temp directory")
    
    def validate_prefect(self, settings: Settings):
        """Validate Prefect configuration."""
        # Check if Prefect server is running
        try:
            import httpx
            prefect_url = os.getenv("PREFECT_API_URL", "http://localhost:4200")
            response = httpx.get(f"{prefect_url}/health", timeout=2.0)
            
            if response.status_code == 200:
                self.info.append("✅ Prefect server is running")
            else:
                self.warnings.append("⚠️  Prefect server not responding - start with: prefect server start")
        except Exception:
            self.warnings.append("⚠️  Cannot connect to Prefect server")
    
    def print_results(self):
        """Print validation results."""
        print("\nVALIDATION RESULTS:")
        print("-" * 60)
        
        # Print info messages
        if self.info:
            print("\nInformation:")
            for msg in self.info:
                print(f"  {msg}")
        
        # Print warnings
        if self.warnings:
            print("\nWarnings:")
            for msg in self.warnings:
                print(f"  {msg}")
        
        # Print errors
        if self.errors:
            print("\nErrors:")
            for msg in self.errors:
                print(f"  {msg}")
        
        # Summary
        print("\n" + "-" * 60)
        print(f"Summary: {len(self.info)} OK, {len(self.warnings)} warnings, {len(self.errors)} errors")
        
        if self.errors:
            print("\n❌ Configuration validation FAILED")
            print("Fix the errors above before running the pipeline.")
        elif self.warnings:
            print("\n⚠️  Configuration validation PASSED with warnings")
            print("The pipeline should work but some features may be limited.")
        else:
            print("\n✅ Configuration validation PASSED")
            print("All systems ready!")


def main():
    """Main entry point."""
    validator = ConfigValidator()
    success = validator.validate_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()