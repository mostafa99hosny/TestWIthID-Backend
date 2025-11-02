from browser import wait_for_element

async def post_login_navigation(page):
    try:
        translate = await wait_for_element(page, "a[href='https://qima.taqeem.sa/setlocale/en']", timeout=10)
        if not translate:
            return {"status": "FAILED", "error": "Translate link not found"}

        return {"status": "SUCCESS"}

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}