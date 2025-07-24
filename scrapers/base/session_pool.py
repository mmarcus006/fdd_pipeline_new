"""Browser session pool for efficient scraping."""

import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, async_playwright

from utils.logging import get_logger
from scrapers.base.exceptions import SessionPoolError


class SessionPool:
    """Manages browser session reuse for faster scraping.
    
    This class implements a pool of browser contexts that can be reused
    across multiple scraping operations, significantly reducing the overhead
    of creating new browser instances for each request.
    """
    
    def __init__(self, max_sessions: int = 3, headless: bool = True):
        self.max_sessions = max_sessions
        self.headless = headless
        self._sessions: List[BrowserContext] = []
        self._available: asyncio.Queue = asyncio.Queue()
        self._browser: Optional[Browser] = None
        self._playwright = None
        self.logger = get_logger(__name__)
        self._initialized = False
        
    async def initialize(self):
        """Initialize the browser and session pool."""
        if self._initialized:
            return
            
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-gpu'
                ]
            )
            
            # Pre-create sessions
            for i in range(self.max_sessions):
                context = await self._browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    extra_http_headers={
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                    }
                )
                self._sessions.append(context)
                await self._available.put(context)
                self.logger.debug(f"Created session {i+1}/{self.max_sessions}")
            
            self._initialized = True
            self.logger.info(f"Session pool initialized with {self.max_sessions} sessions")
            
        except Exception as e:
            raise SessionPoolError(f"Failed to initialize session pool: {e}")
    
    @asynccontextmanager
    async def acquire_session(self):
        """Acquire a browser session from the pool."""
        if not self._initialized:
            await self.initialize()
            
        context = await self._available.get()
        self.logger.debug(f"Acquired session, {self._available.qsize()} remaining")
        
        try:
            yield context
        finally:
            # Clear cookies and storage but keep session alive
            await context.clear_cookies()
            await context.storage_state(path=None)  # Clear storage
            await self._available.put(context)
            self.logger.debug(f"Released session, {self._available.qsize()} available")
    
    async def cleanup(self):
        """Clean up all sessions and browser."""
        if not self._initialized:
            return
            
        self.logger.info("Cleaning up session pool")
        
        # Close all contexts
        for context in self._sessions:
            try:
                await context.close()
            except Exception as e:
                self.logger.error(f"Error closing context: {e}")
        
        # Close browser
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")
        
        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                self.logger.error(f"Error stopping playwright: {e}")
        
        self._sessions.clear()
        self._initialized = False
        self.logger.info("Session pool cleaned up")
    
    def get_stats(self) -> dict:
        """Get session pool statistics."""
        return {
            "total_sessions": self.max_sessions,
            "available_sessions": self._available.qsize(),
            "in_use_sessions": self.max_sessions - self._available.qsize(),
            "initialized": self._initialized
        }