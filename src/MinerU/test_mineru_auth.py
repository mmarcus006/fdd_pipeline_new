"""
Test script to verify MinerU authentication works after fixes
"""
import asyncio
import logging
from mineru_web_api import MinerUWebAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_authentication():
    """Test the authentication process"""
    api = MinerUWebAPI()
    
    try:
        logger.info("Testing MinerU authentication...")
        success = await api.authenticate_with_browser(use_saved_auth=False)
        
        if success:
            logger.info("✅ Authentication successful!")
            logger.info(f"Auth token extracted: {'Yes' if api.auth_token else 'No'}")
            logger.info(f"Cookies extracted: {len(api.cookies)}")
            return True
        else:
            logger.error("❌ Authentication failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Authentication error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_authentication())
    exit(0 if success else 1)