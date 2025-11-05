async def new_window(url: str):
    """Compatibility wrapper for their code"""
    from scripts.core.browser.browser import get_browser
    browser = await get_browser()
    return await browser.get(url)