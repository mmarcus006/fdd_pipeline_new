"""Unit tests for franchise_scrapers.browser module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from franchise_scrapers.browser import get_browser, get_context, with_retry


class TestGetBrowser:
    """Test get_browser function."""
    
    @pytest.mark.asyncio
    async def test_get_browser_success(self):
        """Test successful browser creation."""
        mock_browser = AsyncMock()
        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_chromium
        
        mock_async_playwright = MagicMock()
        mock_async_playwright.return_value.start = AsyncMock(return_value=mock_playwright)
        
        with patch('franchise_scrapers.browser.async_playwright', mock_async_playwright):
            with patch('franchise_scrapers.browser.settings') as mock_settings:
                mock_settings.HEADLESS = True
                mock_settings.DOWNLOAD_DIR = '/test/downloads'
                
                browser = await get_browser()
                
                assert browser == mock_browser
                mock_chromium.launch.assert_called_once_with(
                    headless=True,
                    downloads_path='/test/downloads'
                )
    
    @pytest.mark.asyncio
    async def test_get_browser_headless_false(self):
        """Test browser creation with headless=False."""
        mock_browser = AsyncMock()
        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_chromium
        
        mock_async_playwright = MagicMock()
        mock_async_playwright.return_value.start = AsyncMock(return_value=mock_playwright)
        
        with patch('franchise_scrapers.browser.async_playwright', mock_async_playwright):
            with patch('franchise_scrapers.browser.settings') as mock_settings:
                mock_settings.HEADLESS = False
                mock_settings.DOWNLOAD_DIR = '/test/downloads'
                
                browser = await get_browser()
                
                mock_chromium.launch.assert_called_once_with(
                    headless=False,
                    downloads_path='/test/downloads'
                )


class TestGetContext:
    """Test get_context function."""
    
    @pytest.mark.asyncio
    async def test_get_context_success(self):
        """Test successful context creation."""
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.DOWNLOAD_DIR = '/test/downloads'
            
            context = await get_context(mock_browser)
            
            assert context == mock_context
            
            # Verify context creation parameters
            mock_browser.new_context.assert_called_once()
            call_args = mock_browser.new_context.call_args[1]
            
            assert call_args['viewport'] == {'width': 1280, 'height': 720}
            assert 'Mozilla' in call_args['user_agent']
            assert call_args['accept_downloads'] is True
            
            # Verify timeouts were set
            mock_context.set_default_timeout.assert_called_once_with(30000)
            mock_context.set_default_navigation_timeout.assert_called_once_with(30000)
    
    @pytest.mark.asyncio
    async def test_get_context_custom_download_dir(self):
        """Test context creation with custom download directory."""
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        from pathlib import Path
        test_path = Path('/custom/path')
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.DOWNLOAD_DIR = test_path
            
            await get_context(mock_browser)
            
            # Downloads are configured at browser launch level, not context level
            call_args = mock_browser.new_context.call_args[1]
            assert 'downloads_path' not in call_args


class TestWithRetry:
    """Test with_retry function."""
    
    @pytest.mark.asyncio
    async def test_with_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        async def test_coro(value):
            return value * 2
        
        result = await with_retry(test_coro, 5)
        assert result == 10
    
    @pytest.mark.asyncio
    async def test_with_retry_success_after_failures(self):
        """Test successful execution after initial failures."""
        attempt_count = 0
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception(f"Attempt {attempt_count} failed")
            return "success"
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 3
            mock_settings.PDF_RETRY_BACKOFF = [0.01, 0.01, 0.01]  # Fast for testing
            
            result = await with_retry(test_coro)
            assert result == "success"
            assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_with_retry_all_attempts_fail(self):
        """Test when all retry attempts fail."""
        attempt_count = 0
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception(f"Attempt {attempt_count} failed")
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 3
            mock_settings.PDF_RETRY_BACKOFF = [0.01, 0.01]
            
            with pytest.raises(Exception, match="Attempt 3 failed"):
                await with_retry(test_coro)
            
            assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_with_retry_custom_max_attempts(self):
        """Test with custom max_attempts parameter."""
        attempt_count = 0
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception(f"Attempt {attempt_count}")
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 10  # Default is higher
            mock_settings.PDF_RETRY_BACKOFF = [0.01]
            
            with pytest.raises(Exception, match="Attempt 2"):
                await with_retry(test_coro, max_attempts=2)
            
            assert attempt_count == 2
    
    @pytest.mark.asyncio
    async def test_with_retry_custom_delays(self):
        """Test with custom delays parameter."""
        attempt_count = 0
        sleep_calls = []
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Retry")
            return "success"
        
        async def mock_sleep(delay):
            sleep_calls.append(delay)
        
        with patch('franchise_scrapers.browser.sleep', mock_sleep):
            result = await with_retry(test_coro, delays=[0.1, 0.2, 0.3])
            
            assert result == "success"
            assert sleep_calls == [0.1, 0.2]  # Two retries = two sleeps
    
    @pytest.mark.asyncio
    async def test_with_retry_with_args_and_kwargs(self):
        """Test retry with positional and keyword arguments."""
        async def test_coro(a, b, c=None):
            return f"{a}-{b}-{c}"
        
        result = await with_retry(test_coro, "foo", "bar", c="baz")
        assert result == "foo-bar-baz"
    
    @pytest.mark.asyncio
    async def test_with_retry_exponential_backoff(self):
        """Test exponential backoff behavior."""
        attempt_count = 0
        sleep_calls = []
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 4:
                raise Exception("Retry")
            return "success"
        
        async def mock_sleep(delay):
            sleep_calls.append(delay)
        
        with patch('franchise_scrapers.browser.sleep', mock_sleep):
            with patch('franchise_scrapers.browser.settings') as mock_settings:
                mock_settings.PDF_RETRY_MAX = 5
                mock_settings.PDF_RETRY_BACKOFF = [1.0, 2.0, 4.0]
                
                result = await with_retry(test_coro)
                
                assert result == "success"
                assert sleep_calls == [1.0, 2.0, 4.0]
    
    @pytest.mark.asyncio
    async def test_with_retry_backoff_list_shorter_than_attempts(self):
        """Test when backoff list is shorter than number of attempts."""
        attempt_count = 0
        sleep_calls = []
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 5:
                raise Exception("Retry")
            return "success"
        
        async def mock_sleep(delay):
            sleep_calls.append(delay)
        
        with patch('franchise_scrapers.browser.sleep', mock_sleep):
            with patch('franchise_scrapers.browser.settings') as mock_settings:
                mock_settings.PDF_RETRY_MAX = 5
                mock_settings.PDF_RETRY_BACKOFF = [1.0, 2.0]  # Only 2 delays
                
                result = await with_retry(test_coro)
                
                assert result == "success"
                # Should use last delay for remaining attempts
                assert sleep_calls == [1.0, 2.0, 2.0, 2.0]
    
    @pytest.mark.asyncio
    async def test_with_retry_prints_error_messages(self, capsys):
        """Test that retry prints error messages."""
        attempt_count = 0
        
        async def test_coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError(f"Error on attempt {attempt_count}")
            return "success"
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 3
            mock_settings.PDF_RETRY_BACKOFF = [0.01, 0.01]
            
            await with_retry(test_coro)
            
            captured = capsys.readouterr()
            assert "Retry 1/3" in captured.out
            assert "Error on attempt 1" in captured.out
            assert "Retry 2/3" in captured.out
            assert "Error on attempt 2" in captured.out
    
    @pytest.mark.asyncio
    async def test_with_retry_no_exception_edge_case(self):
        """Test edge case where no exception is stored."""
        # This is a defensive test for the RuntimeError at the end
        async def test_coro():
            return "success"
        
        # Normal execution should work fine
        result = await with_retry(test_coro)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_with_retry_different_exception_types(self):
        """Test retry with different exception types."""
        exceptions = [
            ValueError("Value error"),
            KeyError("Key error"),
            RuntimeError("Runtime error")
        ]
        attempt_count = 0
        
        async def test_coro():
            nonlocal attempt_count
            if attempt_count < len(exceptions):
                exc = exceptions[attempt_count]
                attempt_count += 1
                raise exc
            return "success"
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 4
            mock_settings.PDF_RETRY_BACKOFF = [0.01, 0.01, 0.01]
            
            result = await with_retry(test_coro)
            assert result == "success"
            assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_with_retry_async_generator(self):
        """Test retry with async generator function."""
        attempt_count = 0
        
        async def test_generator():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception("Retry")
            
            for i in range(3):
                yield i
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 2
            mock_settings.PDF_RETRY_BACKOFF = [0.01]
            
            # Note: with_retry returns the generator, not the values
            gen = await with_retry(test_generator)
            values = [val async for val in gen]
            
            assert values == [0, 1, 2]
            assert attempt_count == 2


class TestIntegration:
    """Integration tests for browser module."""
    
    @pytest.mark.asyncio
    async def test_browser_and_context_integration(self):
        """Test creating browser and context together."""
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_chromium
        
        mock_async_playwright = MagicMock()
        mock_async_playwright.return_value.start = AsyncMock(return_value=mock_playwright)
        
        with patch('franchise_scrapers.browser.async_playwright', mock_async_playwright):
            with patch('franchise_scrapers.browser.settings') as mock_settings:
                mock_settings.HEADLESS = True
                mock_settings.DOWNLOAD_DIR = '/downloads'
                
                browser = await get_browser()
                context = await get_context(browser)
                
                assert browser == mock_browser
                assert context == mock_context
    
    @pytest.mark.asyncio
    async def test_retry_with_browser_operations(self):
        """Test retry functionality with browser-like operations."""
        attempt_count = 0
        
        async def navigate_and_scrape(url):
            nonlocal attempt_count
            attempt_count += 1
            
            if attempt_count == 1:
                raise TimeoutError("Page load timeout")
            elif attempt_count == 2:
                raise Exception("Network error")
            
            return {"data": "scraped", "url": url}
        
        with patch('franchise_scrapers.browser.settings') as mock_settings:
            mock_settings.PDF_RETRY_MAX = 3
            mock_settings.PDF_RETRY_BACKOFF = [0.01, 0.01]
            
            result = await with_retry(
                navigate_and_scrape,
                "https://example.com"
            )
            
            assert result == {"data": "scraped", "url": "https://example.com"}
            assert attempt_count == 3