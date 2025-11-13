import asyncio
from scripts.core.browser.utils import log, wait_for_element
from scripts.core.browser.browser import new_window
from .reportInfo import extract_report_info
from .pagination import go_to_last_asset_page
from .assetDelete import delete_latest_asset

OFFICE_ID = "487"  # TODO: Move to config
MACROS_INPUT_SEL = "#macros"
SAVE_BTN_SEL = "input.btn.btn-primary.btn-lg.mt-2[type='submit'][value='Save']"
CANCELLED_VALUES = {"ملغى", "ملغي", "Canceled", "Cancelled"}

async def _set_macros_to_one(page) -> bool:
    """Set the 'Number of Macros' input to 1"""
    try:
        ok = await page.evaluate("""
            (() => {
              const el = document.querySelector('#macros');
              if (!el) return false;
              el.removeAttribute('readonly');
              el.removeAttribute('disabled');
              el.value = 1;
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              return true;
            })()
        """)
        return bool(ok)
    except Exception as e:
        log(f"Failed to set macros via JS: {e}", "WARN")
        return False

async def _click_save(page) -> bool:
    """Click the Save button (supports English 'Save' and Arabic 'حفظ')"""
    # Try the standard English button first
    btn = await wait_for_element(page, SAVE_BTN_SEL, timeout=12)
    if btn:
        try:
            await btn.click()
            return True
        except Exception as e:
            log(f"Primary Save click failed: {e}", "WARN")

    # Fallbacks: support both English and Arabic save buttons
    try:
        ok = await page.evaluate("""
            (() => {
              const texts = ["Save", "حفظ"];
              const candidates = Array.from(
                document.querySelectorAll('input[type=submit], button')
              );
              for (const el of candidates) {
                const v = (el.value || el.textContent || '').trim();
                if (texts.some(t => v.includes(t))) {
                  el.click();
                  return true;
                }
              }
              return false;
            })()
        """)
        if ok:
            log("Clicked Arabic/English Save button successfully.", "OK")
            return True
    except Exception as e:
        log(f"Fallback Arabic/English Save click failed: {e}", "ERR")
        return False

    log("No Save button found (English or Arabic).", "ERR")
    return False

async def _create_single_macro(report_id: str) -> bool:
    """
    Create exactly 1 macro for the given report, click Save,
    navigate to the last page where the new asset appears,
    then delete it.
    """
    create_url = f"https://qima.taqeem.sa/report/asset/create/{report_id}"
    log(f"Navigating to asset-create page: {create_url}", "STEP")
    page = await new_window(create_url)
    await asyncio.sleep(1.5)

    # Wait for the "Number of Macros" input
    macros_input = await wait_for_element(page, MACROS_INPUT_SEL, timeout=25)
    if not macros_input:
        log("Could not find Number of Macros input (#macros).", "ERR")
        return False

    # Set macros=1
    if not await _set_macros_to_one(page):
        log("Failed to set Number of Macros to 1.", "ERR")
        return False

    # Click Save (supports English 'Save' and Arabic 'حفظ')
    if not await _click_save(page):
        log("Save button not found/click failed on asset-create page.", "ERR")
        return False

    log("Clicked Save to create 1 macro.", "OK")
    await asyncio.sleep(1.0)

    # After save, move to the last available page(s) where the new asset appears
    try:
        await go_to_last_asset_page(report_id, page)
    except Exception as e:
        log(f"Pagination to last asset page failed: {e}", "WARN")

    # Delete the newly created asset
    try:
        ok_del = await delete_latest_asset(report_id, page)
        if ok_del:
            log("Newest asset deleted successfully.", "OK")
        else:
            log("Failed to delete newest asset.", "ERR")
    except Exception as e:
        log(f"Delete latest asset errored: {e}", "ERR")

    return True

async def handle_cancelled_report(report_id: str, control_state=None) -> dict:
    """
    Check if a single report is cancelled. If yes, create and delete a macro to update status.
    
    Args:
        report_id: The report ID to check
        control_state: Optional control state for cancellation checks
    
    Returns:
        dict: {
            "status": "CREATED_AND_DELETED" | "NOT_CANCELLED" | "FAILED",
            "reportId": str,
            "wasCancelled": bool,
            "message": str
        }
    """
    try:
        # Open report page
        url = f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}"
        log(f"Opening report: {url}", "STEP")
        page = await new_window(url)
        await asyncio.sleep(2.0)

        # Check control state
        if control_state and control_state.is_cancelled():
            log(f"Operation cancelled while processing report {report_id}", "INFO")
            return {
                "status": "FAILED",
                "reportId": report_id,
                "wasCancelled": False,
                "error": "Operation cancelled"
            }

        await asyncio.sleep(1.2)  # let DOM render

        # Extract report info
        info = await extract_report_info(page)
        if not info.get("found"):
            log(f"Report {report_id}: report details not found.", "ERR")
            return {
                "status": "FAILED",
                "reportId": report_id,
                "wasCancelled": False,
                "error": "Report details not found"
            }

        alias = info.get("alias") or {}
        status_val = (alias.get("status") or {}).get("value") or ""
        log(f"Report {report_id} status = {status_val!r}", "INFO")

        # Check if cancelled
        if status_val not in CANCELLED_VALUES:
            log(f"Report {report_id} is not cancelled — no macro creation needed.", "INFO")
            return {
                "status": "NOT_CANCELLED",
                "reportId": report_id,
                "wasCancelled": False,
                "currentStatus": status_val,
                "message": "Report is not cancelled"
            }

        # Report is cancelled - create and delete macro
        log(f"Report {report_id} is cancelled ({status_val}) → creating and deleting 1 macro.", "STEP")
        ok = await _create_single_macro(report_id)
        
        if ok:
            log(f"Report {report_id}: macro creation and deletion flow finished.", "OK")
            return {
                "status": "CHANGED",
                "reportId": report_id,
                "wasCancelled": True,
                "previousStatus": status_val,
                "message": "Changed status for report"
            }
        else:
            log(f"Report {report_id}: macro creation flow failed.", "ERR")
            return {
                "status": "FAILED",
                "reportId": report_id,
                "wasCancelled": True,
                "previousStatus": status_val,
                "error": "Failed to change status"
            }

    except Exception as e:
        log(f"Error processing report {report_id}: {e}", "ERR")
        return {
            "status": "FAILED",
            "reportId": report_id,
            "wasCancelled": False,
            "error": str(e)
        }