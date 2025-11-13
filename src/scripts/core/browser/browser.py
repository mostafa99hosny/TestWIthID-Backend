from nodriver import Browser
from .utils import log
from urllib.parse import urlparse

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

async def create_new_browser_window():
    browser = await get_browser()
    new_page = await browser.get("https://qima.taqeem.sa/", new_window=True)
    log(f"Created new browser window with URL: {await new_page.evaluate('window.location.href')}", "INFO")
    return new_page

def _is_valid_http_url(url: str) -> bool:
    try:
        parts = urlparse(url)
        return parts.scheme in ("http", "https") and bool(parts.netloc)
    except Exception:
        return False

async def get_page():
    browser = await get_browser()
    return browser.main_tab

async def navigate(url: str):
    def _sanitize(u: str) -> str:
        return (u or "").strip().strip('"\\' + "'")

    url = _sanitize(url)
    browser = await get_browser()

    if not _is_valid_http_url(url):
        log(f"Invalid URL -> '{url}'", "ERR")
        page = await browser.new_page()
        return page

    # Try once, then restart browser and retry once more if transport fails
    for attempt in range(2):
        try:
            return await browser.get(url)
        except Exception as e:
            log(f"browser.get() failed (try {attempt+1}/2): {e}", "WARN")
            try:
                page = await browser.new_page()
                await page.evaluate("url => { window.location.href = url; }", url)
                return page
            except Exception as e2:
                log(f"fallback window.location failed: {e2}", "WARN")
                if attempt == 0:
                    # restart browser and retry
                    try:
                        await closeBrowser()
                    except Exception:
                        pass
                    # get_browser() will recreate
                    browser = await get_browser()
                else:
                    # give up with a blank page
                    try:
                        return await browser.new_page()
                    except Exception:
                        raise

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
    """Check if browser instance exists, is active, and user is logged in"""
    global _browser
    if _browser is None:
        return {"status": "FAILED", "error": "No browser instance", "browserOpen": False}
    
    try:
        page = _browser.main_tab
        url = await page.evaluate("window.location.href")  # Fixed: evaluate not evaulate
        current_url = url.lower()
        
        # URLs that definitively indicate NOT logged in
        non_logged_in_urls = [
            "sso.taqeem.gov.sa/realms/rel_taqeem/login-actions/authenticate",
            "sso.taqeem.gov.sa/realms/rel_taqeem/protocol/openid-connect/auth",
            "/login-actions/authenticate",
            "/protocol/openid-connect/auth"
        ]
        
        # If we're on any authentication URL, we're definitely not logged in
        if any(auth_url in current_url for auth_url in non_logged_in_urls):
            return {"status": "FAILED", "error": "User not logged in", "browserOpen": True}
            
        # If browser is responsive and we're NOT on auth URLs, assume logged in
        return {"status": "SUCCESS", "message": "User is logged in", "browserOpen": True}
        
    except Exception as e:
        # Browser instance exists but is not actually running
        _browser = None
        return {"status": "FAILED", "error": str(e), "browserOpen": False}

async def wait_for_element(page, selector, timeout=30):
    """Wait for element with timeout"""
    try:
        element = await page.select(selector, timeout=timeout)
        return element
    except Exception as e:
        print(f"Warning: Element not found: {selector} - {e}")
        return None
    
async def new_window(url: str | None = None):
    if url:
        return await navigate(url)
    browser = await get_browser()
    return await browser.new_page()