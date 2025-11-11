from nodriver import Browser

_browser = None

async def get_browser(force_new=False):
    global _browser
    if force_new and _browser:
        await closeBrowser()
    
    if not _browser:
        # Simple initialization without complex config
        _browser = await Browser.create(
            headless=False,  # Set to True for headless mode
            # browser_path=None,  # Custom browser path if needed
            # user_data_dir=None,  # Custom user data directory
            # args=None  # Additional browser arguments
        )
    
    return _browser

async def get_page():
    browser = await get_browser()
    return browser.main_tab

async def set_page(page):
    # For compatibility - not needed with nodriver
    pass

async def closeBrowser():
    global _browser
    if _browser:
        try:
            await _browser.stop()
        except Exception as e:
            print(f"Warning: Error closing browser: {e}")
        finally:
            _browser = None

async def is_browser_open():
    """Check if browser instance exists and is active"""
    global _browser
    if _browser is None:
        return False
    
    try:
        # Try to access the browser's main tab to verify it's actually running
        # If the browser was closed externally, this will fail
        _ = _browser.main_tab
        return True
    except Exception:
        # Browser instance exists but is not actually running
        _browser = None
        return False

async def wait_for_element(page, selector, timeout=30):
    """Wait for element with timeout"""
    try:
        element = await page.select(selector, timeout=timeout)
        return element
    except Exception as e:
        print(f"Warning: Element not found: {selector} - {e}")
        return None