"""Unit tests for franchise_scrapers.config module."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from franchise_scrapers.config import Settings


class TestSettings:
    """Test Settings class initialization and validation."""
    
    @pytest.fixture
    def clean_env(self):
        """Fixture to clean environment variables."""
        # Store original environment
        original_env = os.environ.copy()
        
        # Clear relevant env vars
        env_vars = [
            'HEADLESS', 'DOWNLOAD_DIR', 'THROTTLE_SEC',
            'PDF_RETRY_MAX', 'PDF_RETRY_BACKOFF', 'MAX_WORKERS'
        ]
        for var in env_vars:
            os.environ.pop(var, None)
        
        yield
        
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
    
    def test_default_settings(self, clean_env):
        """Test Settings with default values."""
        settings = Settings()
        
        assert settings.HEADLESS is True
        assert settings.DOWNLOAD_DIR == Path("./downloads")
        assert settings.THROTTLE_SEC == 0.5
        assert settings.PDF_RETRY_MAX == 3
        assert settings.PDF_RETRY_BACKOFF == [1.0, 2.0, 4.0]
        assert settings.MAX_WORKERS == 4
    
    def test_settings_from_environment(self, clean_env):
        """Test Settings loading from environment variables."""
        os.environ['HEADLESS'] = 'false'
        os.environ['DOWNLOAD_DIR'] = '/tmp/test_downloads'
        os.environ['THROTTLE_SEC'] = '2.5'
        os.environ['PDF_RETRY_MAX'] = '5'
        os.environ['PDF_RETRY_BACKOFF'] = '0.5,1.5,3.0,6.0'
        os.environ['MAX_WORKERS'] = '8'
        
        settings = Settings()
        
        assert settings.HEADLESS is False
        assert settings.DOWNLOAD_DIR == Path('/tmp/test_downloads')
        assert settings.THROTTLE_SEC == 2.5
        assert settings.PDF_RETRY_MAX == 5
        assert settings.PDF_RETRY_BACKOFF == [0.5, 1.5, 3.0, 6.0]
        assert settings.MAX_WORKERS == 8
    
    def test_headless_parsing(self, clean_env):
        """Test HEADLESS environment variable parsing."""
        # Test various true values
        for value in ['true', 'True', 'TRUE', '1', 'yes']:
            os.environ['HEADLESS'] = value
            settings = Settings()
            assert settings.HEADLESS is True
        
        # Test various false values
        for value in ['false', 'False', 'FALSE', '0', 'no']:
            os.environ['HEADLESS'] = value
            settings = Settings()
            assert settings.HEADLESS is False
    
    def test_download_dir_creation(self, clean_env, tmp_path):
        """Test that DOWNLOAD_DIR is created if it doesn't exist."""
        test_dir = tmp_path / "new_download_dir"
        assert not test_dir.exists()
        
        os.environ['DOWNLOAD_DIR'] = str(test_dir)
        settings = Settings()
        
        assert test_dir.exists()
        assert test_dir.is_dir()
        assert settings.DOWNLOAD_DIR == test_dir
    
    def test_parse_backoff_valid(self, clean_env):
        """Test parsing valid backoff strings."""
        test_cases = [
            ("1,2,4", [1.0, 2.0, 4.0]),
            ("0.5, 1.0, 2.0", [0.5, 1.0, 2.0]),
            ("1", [1.0]),
            ("1.5,3.0,6.0,12.0,24.0", [1.5, 3.0, 6.0, 12.0, 24.0]),
            (" 1 , 2 , 4 ", [1.0, 2.0, 4.0]),  # With spaces
        ]
        
        for backoff_str, expected in test_cases:
            os.environ['PDF_RETRY_BACKOFF'] = backoff_str
            settings = Settings()
            assert settings.PDF_RETRY_BACKOFF == expected
    
    def test_parse_backoff_invalid(self, clean_env):
        """Test parsing invalid backoff strings falls back to default."""
        test_cases = [
            "not,a,number",
            "1,2,three",
            "",
            "1.0.0",
            "a,b,c",
        ]
        
        for backoff_str in test_cases:
            os.environ['PDF_RETRY_BACKOFF'] = backoff_str
            settings = Settings()
            # Should fall back to default
            assert settings.PDF_RETRY_BACKOFF == [1.0, 2.0, 4.0]
    
    def test_validation_throttle_sec(self, clean_env):
        """Test THROTTLE_SEC validation."""
        # Valid values
        os.environ['THROTTLE_SEC'] = '0'
        settings = Settings()
        assert settings.THROTTLE_SEC == 0.0
        
        os.environ['THROTTLE_SEC'] = '10.5'
        settings = Settings()
        assert settings.THROTTLE_SEC == 10.5
        
        # Invalid value
        os.environ['THROTTLE_SEC'] = '-1'
        with pytest.raises(ValueError, match="THROTTLE_SEC must be non-negative"):
            Settings()
    
    def test_validation_pdf_retry_max(self, clean_env):
        """Test PDF_RETRY_MAX validation."""
        # Valid values
        os.environ['PDF_RETRY_MAX'] = '1'
        settings = Settings()
        assert settings.PDF_RETRY_MAX == 1
        
        os.environ['PDF_RETRY_MAX'] = '10'
        settings = Settings()
        assert settings.PDF_RETRY_MAX == 10
        
        # Invalid values
        os.environ['PDF_RETRY_MAX'] = '0'
        with pytest.raises(ValueError, match="PDF_RETRY_MAX must be at least 1"):
            Settings()
        
        os.environ['PDF_RETRY_MAX'] = '-5'
        with pytest.raises(ValueError, match="PDF_RETRY_MAX must be at least 1"):
            Settings()
    
    def test_validation_pdf_retry_backoff(self, clean_env):
        """Test PDF_RETRY_BACKOFF validation."""
        # Empty backoff list should fail
        with patch.object(Settings, '_parse_backoff', return_value=[]):
            with pytest.raises(ValueError, match="PDF_RETRY_BACKOFF must contain at least one value"):
                Settings()
    
    def test_validation_max_workers(self, clean_env):
        """Test MAX_WORKERS validation."""
        # Valid values
        os.environ['MAX_WORKERS'] = '1'
        settings = Settings()
        assert settings.MAX_WORKERS == 1
        
        os.environ['MAX_WORKERS'] = '16'
        settings = Settings()
        assert settings.MAX_WORKERS == 16
        
        # Invalid values
        os.environ['MAX_WORKERS'] = '0'
        with pytest.raises(ValueError, match="MAX_WORKERS must be at least 1"):
            Settings()
        
        os.environ['MAX_WORKERS'] = '-2'
        with pytest.raises(ValueError, match="MAX_WORKERS must be at least 1"):
            Settings()
    
    def test_type_conversions(self, clean_env):
        """Test type conversions for numeric values."""
        # Float conversion
        os.environ['THROTTLE_SEC'] = '1.234'
        settings = Settings()
        assert settings.THROTTLE_SEC == 1.234
        assert isinstance(settings.THROTTLE_SEC, float)
        
        # Int conversion
        os.environ['PDF_RETRY_MAX'] = '7'
        settings = Settings()
        assert settings.PDF_RETRY_MAX == 7
        assert isinstance(settings.PDF_RETRY_MAX, int)
        
        # Invalid numeric values
        os.environ['THROTTLE_SEC'] = 'abc'
        with pytest.raises(ValueError):
            Settings()
        
        os.environ['THROTTLE_SEC'] = '0.5'  # Reset to valid
        os.environ['MAX_WORKERS'] = 'not-a-number'
        with pytest.raises(ValueError):
            Settings()
    
    def test_settings_immutability(self, clean_env):
        """Test that settings values can be modified after creation."""
        settings = Settings()
        
        # Test modifying values
        original_throttle = settings.THROTTLE_SEC
        settings.THROTTLE_SEC = 5.0
        assert settings.THROTTLE_SEC == 5.0
        
        # Test modifying lists
        original_backoff = settings.PDF_RETRY_BACKOFF.copy()
        settings.PDF_RETRY_BACKOFF.append(8.0)
        assert len(settings.PDF_RETRY_BACKOFF) == len(original_backoff) + 1
    
    def test_dotenv_loading(self, clean_env, tmp_path):
        """Test that dotenv files are loaded if present."""
        # Create a .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
HEADLESS=false
DOWNLOAD_DIR=/custom/downloads
THROTTLE_SEC=3.0
PDF_RETRY_MAX=2
MAX_WORKERS=6
""")
        
        # Change to the temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Reload the module to trigger dotenv loading
            import importlib
            import franchise_scrapers.config
            importlib.reload(franchise_scrapers.config)
            
            # Create new settings instance
            settings = franchise_scrapers.config.Settings()
            
            # Verify values from .env file
            assert settings.HEADLESS is False
            assert settings.DOWNLOAD_DIR == Path("/custom/downloads")
            assert settings.THROTTLE_SEC == 3.0
            assert settings.PDF_RETRY_MAX == 2
            assert settings.MAX_WORKERS == 6
            
        finally:
            os.chdir(original_cwd)
    
    def test_path_object_behavior(self, clean_env):
        """Test Path object behavior for DOWNLOAD_DIR."""
        os.environ['DOWNLOAD_DIR'] = './test/downloads'
        settings = Settings()
        
        # Should be a Path object
        assert isinstance(settings.DOWNLOAD_DIR, Path)
        
        # Test Path operations
        assert settings.DOWNLOAD_DIR.name == 'downloads'
        assert settings.DOWNLOAD_DIR.parent.name == 'test'
        
        # Test joining paths
        pdf_path = settings.DOWNLOAD_DIR / 'test.pdf'
        assert str(pdf_path).endswith('test.pdf')
    
    def test_edge_cases(self, clean_env):
        """Test edge cases and boundary values."""
        # Very large values
        os.environ['THROTTLE_SEC'] = '999999.999'
        os.environ['PDF_RETRY_MAX'] = '1000'
        os.environ['MAX_WORKERS'] = '1000'
        
        settings = Settings()
        assert settings.THROTTLE_SEC == 999999.999
        assert settings.PDF_RETRY_MAX == 1000
        assert settings.MAX_WORKERS == 1000
        
        # Very small valid values
        os.environ['THROTTLE_SEC'] = '0.001'
        settings = Settings()
        assert settings.THROTTLE_SEC == 0.001
        
        # Whitespace in environment values
        os.environ['HEADLESS'] = '  true  '
        os.environ['DOWNLOAD_DIR'] = '  ./downloads  '
        settings = Settings()
        assert settings.HEADLESS is True
        # Path constructor handles whitespace
    
    def test_multiple_instances(self, clean_env):
        """Test creating multiple Settings instances."""
        os.environ['MAX_WORKERS'] = '4'
        settings1 = Settings()
        
        os.environ['MAX_WORKERS'] = '8'
        settings2 = Settings()
        
        # Each instance reads environment at creation time
        assert settings1.MAX_WORKERS == 4
        assert settings2.MAX_WORKERS == 8
    
    def test_settings_singleton_pattern(self, clean_env):
        """Test the module-level settings instance."""
        from franchise_scrapers.config import settings
        
        # Should be a Settings instance
        assert isinstance(settings, Settings)
        
        # Should have default values (assuming clean environment)
        assert settings.HEADLESS is True
        assert settings.MAX_WORKERS == 4


class TestSettingsIntegration:
    """Integration tests for Settings with other components."""
    
    def test_download_dir_permissions(self, tmp_path):
        """Test that created directories have correct permissions."""
        test_dir = tmp_path / "test_permissions"
        
        os.environ['DOWNLOAD_DIR'] = str(test_dir)
        settings = Settings()
        
        # Directory should be readable and writable
        assert os.access(settings.DOWNLOAD_DIR, os.R_OK)
        assert os.access(settings.DOWNLOAD_DIR, os.W_OK)
        
        # Should be able to create files in the directory
        test_file = settings.DOWNLOAD_DIR / "test.txt"
        test_file.write_text("test content")
        assert test_file.exists()
    
    def test_nested_directory_creation(self, tmp_path):
        """Test creation of nested directories."""
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        
        os.environ['DOWNLOAD_DIR'] = str(nested_dir)
        settings = Settings()
        
        assert nested_dir.exists()
        assert nested_dir.is_dir()
        
        # All parent directories should exist
        assert (tmp_path / "level1").exists()
        assert (tmp_path / "level1" / "level2").exists()