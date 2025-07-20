# franchise_scrapers/browser.py
from asyncio import sleep
from typing import Any, Callable, TypeVar, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext

from .config import settings

T = TypeVar('T')


async def get_browser() -> Browser:
    """Create and return a configured browser instance.
    
    Returns:
        Browser: Configured Playwright browser instance
    """
    playwright = await async_playwright().start()
    return await playwright.chromium.launch(
        headless=settings.HEADLESS,
        downloads_path=str(settings.DOWNLOAD_DIR)
    )


async def get_context(browser: Browser) -> BrowserContext:
    """Create a browser context with download configuration.
    
    Args:
        browser: Browser instance from get_browser()
        
    Returns:
        BrowserContext: Configured browser context
    """
    context = await browser.new_context(
        viewport={'width': 1280, 'height': 720},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        accept_downloads=True,
    )
    
    # Set default timeouts
    context.set_default_timeout(30000)  # 30 seconds
    context.set_default_navigation_timeout(30000)  # 30 seconds
    
    return context


async def with_retry(
    coro: Callable[..., T], 
    *args, 
    max_attempts: Optional[int] = None,
    delays: Optional[list[float]] = None,
    **kwargs
) -> T:
    """Execute coroutine with exponential backoff retry.
    
    Args:
        coro: Async function to retry
        *args: Positional arguments for coro
        max_attempts: Override max retry attempts
        delays: Override retry delays
        **kwargs: Keyword arguments for coro
        
    Returns:
        Result from successful coroutine execution
        
    Raises:
        Exception: Last exception after all retries exhausted
    """
    if max_attempts is None:
        max_attempts = settings.PDF_RETRY_MAX
    
    if delays is None:
        delays = settings.PDF_RETRY_BACKOFF
    
    last_exc = None
    
    for attempt in range(max_attempts):
        try:
            return await coro(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            
            # Don't retry on last attempt
            if attempt >= max_attempts - 1:
                raise
            
            # Get delay for this attempt
            delay_idx = min(attempt, len(delays) - 1)
            delay = delays[delay_idx]
            
            print(f"Retry {attempt + 1}/{max_attempts} after {delay}s - Error: {exc}")
            await sleep(delay)
    
    # Should never reach here, but just in case
    if last_exc:
        raise last_exc
    raise RuntimeError("Retry failed with no exception")