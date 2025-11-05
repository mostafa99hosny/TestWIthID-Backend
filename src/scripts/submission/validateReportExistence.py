import asyncio, sys, traceback, json
from scripts.core.browser.browser import get_browser
from scripts.core.browser.utils import wait_for_table_rows

async def validate_report(cmd):
    report_id = cmd.get("reportId")
    if not report_id:
        return {
            "status": "FAILED",
            "error": "Missing reportId in command"
        }

    url = f"https://qima.taqeem.sa/report/{report_id}"
    print(f"[VALIDATION] Checking report existence for {report_id}", file=sys.stderr)

    try:
        browser = await get_browser()
        page = browser.main_tab

        # Navigate to the report URL
        await page.get(url)
        await asyncio.sleep(3)  # wait for page content to load

        html = await page.get_content()

        # Check for different error scenarios
        error_text_1 = "ليس لديك صلاحية للتواجد هنا !"  # "You do not have permission to be here!"
        error_text_2 = "هذه الصفحة غير موجودة!"  # "This page does not exist! Did you reach it by mistake?"

        if error_text_1 in html or error_text_2 in html:
            result = {
                "status": "NOT_FOUND",
                "message": "Report not accessible or does not exist",
                "reportId": report_id,
                "exists": False,
                "url": url,
            }
        else:
            # Report exists - now check for macros table
            macros_table = await wait_for_table_rows(page, timeout=5)
            print("macros_table:", macros_table)
            
            if macros_table:
                result = {
                    "status": "MACROS_EXIST", 
                    "message": "Only works with empty reports",
                    "reportId": report_id,
                    "exists": True,
                    "url": url,
                    "hasMacros": True
                }
            else:
                result = {
                    "status": "SUCCESS", 
                    "message": "Report appears to exist and is accessible",
                    "reportId": report_id,
                    "exists": True,
                    "url": url,
                    "hasMacros": False
                }

        print(f"[VALIDATION] Completed check for {report_id}", file=sys.stderr)
        return result

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[VALIDATION] Error checking report {report_id}: {e}", file=sys.stderr)
        return {
            "status": "FAILED",
            "reportId": report_id,
            "error": str(e),
            "traceback": tb,
        }

async def wait_for_element(page, selector, timeout=30):
    """Wait for element with timeout"""
    try:
        element = await page.select(selector, timeout=timeout)
        return element
    except Exception as e:
        print(f"Warning: Element not found: {selector} - {e}")
        return None