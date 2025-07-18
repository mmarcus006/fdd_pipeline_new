"""
Quick test script to verify Chrome installation and profile paths
"""
import os

# Chrome paths
CHROME_CANARY_EXE = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\Application\chrome.exe")
CHROME_USER_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\User Data")
CHROME_STABLE_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")

print("Chrome Path Check:")
print("-" * 50)

# Check Chrome Canary
print(f"Chrome Canary Exe: {CHROME_CANARY_EXE}")
print(f"  Exists: {os.path.exists(CHROME_CANARY_EXE)}")

print(f"\nChrome Canary User Data: {CHROME_USER_DATA_DIR}")
print(f"  Exists: {os.path.exists(CHROME_USER_DATA_DIR)}")

# Check regular Chrome
print(f"\nChrome Stable User Data: {CHROME_STABLE_USER_DATA}")
print(f"  Exists: {os.path.exists(CHROME_STABLE_USER_DATA)}")

# Check for Chrome executable in various locations
chrome_paths = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
]

print("\nChecking Chrome executable locations:")
for path in chrome_paths:
    print(f"  {path}: {'EXISTS' if os.path.exists(path) else 'NOT FOUND'}")

# List profiles if Chrome user data exists
if os.path.exists(CHROME_STABLE_USER_DATA):
    print(f"\nProfiles in Chrome user data:")
    try:
        for item in os.listdir(CHROME_STABLE_USER_DATA):
            item_path = os.path.join(CHROME_STABLE_USER_DATA, item)
            if os.path.isdir(item_path) and (item == "Default" or item.startswith("Profile")):
                print(f"  - {item}")
    except Exception as e:
        print(f"  Error listing profiles: {e}")

if os.path.exists(CHROME_USER_DATA_DIR):
    print(f"\nProfiles in Chrome Canary user data:")
    try:
        for item in os.listdir(CHROME_USER_DATA_DIR):
            item_path = os.path.join(CHROME_USER_DATA_DIR, item)
            if os.path.isdir(item_path) and (item == "Default" or item.startswith("Profile")):
                print(f"  - {item}")
    except Exception as e:
        print(f"  Error listing profiles: {e}")