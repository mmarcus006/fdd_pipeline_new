# save_auth_state.py
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

AUTH_FILE = "auth.json"

# Chrome paths (Windows default)
CHROME_CANARY_EXE = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\Application\chrome.exe")
CHROME_USER_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\User Data")
CHROME_STABLE_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")

def get_chrome_profile():
    """Find Chrome installation and profile directory
    
    Returns:
        Tuple of (user_data_dir, executable_path)
    """
    # Check for Chrome Canary first
    if os.path.exists(CHROME_CANARY_EXE) and os.path.exists(CHROME_USER_DATA_DIR):
        print("Found Chrome Canary installation")
        return CHROME_USER_DATA_DIR, CHROME_CANARY_EXE
    
    # Fall back to regular Chrome
    if os.path.exists(CHROME_STABLE_USER_DATA):
        print("Chrome Canary not found, using regular Chrome")
        # Look for Chrome executable
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
        for chrome_exe in chrome_paths:
            if os.path.exists(chrome_exe):
                return CHROME_STABLE_USER_DATA, chrome_exe
    
    return None, None

async def main():
    """
    Launches a browser for the user to manually log into GitHub.
    Saves the authentication state (cookies, local storage) to a file
    for subsequent automated runs.
    """
    # Get Chrome profile
    user_data_dir, chrome_exe = get_chrome_profile()
    
    async with async_playwright() as p:
        if user_data_dir and chrome_exe:
            print(f"Using Chrome profile: {user_data_dir}")
            print(f"Chrome executable: {chrome_exe}")
            # Use persistent context to load existing profile
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=chrome_exe,
                headless=False,
                channel=None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ],
                viewport=None,
                ignore_default_args=["--enable-automation"]
            )
        else:
            # Fall back to regular browser if no profile found
            print("Warning: Could not find Chrome installation. Using default Chromium.")
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
        
        page = await context.new_page()

        print("\n" + "="*60)
        print("A Chrome window will open. Please log in to GitHub.")
        print("After you have successfully logged in, you can close the browser.")
        print("Your authentication state will be saved for future script runs.")
        print("="*60 + "\n")
        
        await page.goto("https://github.com/login")
        
        # This will pause the script until the browser window is closed by the user.
        await page.wait_for_event("close")

        # Save the authentication state to the specified file.
        await context.storage_state(path=AUTH_FILE)
        print(f"Authentication state successfully saved to '{AUTH_FILE}'!")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())