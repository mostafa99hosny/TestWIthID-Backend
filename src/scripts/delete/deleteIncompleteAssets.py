import asyncio, re, json
from scripts.core.browser.utils import log

TABLE_CSS = "#m-table"
ROW_CSS   = "#m-table tbody tr"

TBODY_XPATH_FALLBACK = "/html/body/div/div[5]/div[2]/div/div[8]/div/div/div/div[2]/div[2]/table/tbody"

INCOMPLETE_AR = "غير مكتملة"
macro_link_re = re.compile(r"/report/macro/(\d+)/(?:show|edit|delete)")

# DataTables subpage pagination
DATATABLE_NEXT_SEL = (
    'a.paginate_button.next#m-table_next, '
    'a.paginate_button.next[aria-controls="m-table"], '
    '#m-table_next, '
    'a.paginate_button.next'
)
DATATABLE_PREV_SEL = (
    'a.paginate_button.previous#m-table_previous, '
    'a.paginate_button.previous[aria-controls="m-table"], '
    '#m-table_previous, '
    'a.paginate_button.previous'
)

# Main (outer) pagination
MAIN_NEXT_SEL = 'a.page-link[rel="next"]'


async def _debug_table_snapshot(page):
    table = await page.find(TABLE_CSS)
    log(f"[debug] table {TABLE_CSS} present: {bool(table)}", "INFO")
    if table:
        tbody = await table.find("tbody")
        log(f"[debug] tbody under {TABLE_CSS}: {bool(tbody)}", "INFO")
        if tbody:
            rows = await tbody.find_all("tr")
            log(f"[debug] row count via CSS: {len(rows or [])}", "INFO")
    try:
        tbody2 = await page.find_xpath(TBODY_XPATH_FALLBACK)
        log(f"[debug] tbody via XPATH present: {bool(tbody2)}", "INFO")
        if tbody2:
            rows2 = await tbody2.find_all("tr")
            log(f"[debug] row count via XPATH: {len(rows2 or [])}", "INFO")
    except Exception as e:
        log(f"[debug] tbody XPATH lookup error: {e}", "ERR")


async def _find_rows(page):
    """Try CSS (#m-table tbody tr) then fallback XPath."""
    rows = await page.find_all(ROW_CSS)
    if rows and len(rows) > 0:
        log(f"[table-scan] Found {len(rows)} rows via CSS", "INFO")
        return rows

    try:
        tbody = await page.find_xpath(TBODY_XPATH_FALLBACK)
        if tbody:
            xrows = await tbody.find_all("tr")
            if xrows and len(xrows) > 0:
                log(f"[table-scan] Found {len(xrows)} rows via XPATH", "INFO")
                return xrows
    except Exception as e:
        log(f"[table-scan] XPATH error: {e}", "ERR")

    log("No rows found.", "ERR")
    await _debug_table_snapshot(page)
    return []

async def _parse_asset_rows(page):

    assets = []
    non_assets = 0

    rows = await _find_rows(page)
    if not rows:
        log("No rows found", "ERR")
        return assets, non_assets

    preview_cap = 4
    for idx, row in enumerate(rows, start=1):
        try:
            html = (await row.get_html()) or ""
        except Exception as e:
            log(f"[row {idx}] failed to get html: {e}", "ERR")
            continue

        if idx <= preview_cap:
            log(f"[row {idx} preview] {html[:200].replace(chr(10),' ')}…", "INFO")

        m = re.search(r'href="https?://[^"]*/report/macro/(\d+)/(?:show|edit|delete)"', html)
        if not m:
            m = macro_link_re.search(html)

        macro_id = m.group(1) if m else None
        is_incomplete = (INCOMPLETE_AR in html)

        if macro_id:
            assets.append({
                "idx": idx,
                "macro_id": macro_id,
                "incomplete": is_incomplete
            })
            log(f"[row {idx}] ASSET macro_id={macro_id} incomplete={is_incomplete}", "INFO")
        else:
            non_assets += 1
            log(f"[row {idx}] NON-ASSET row", "INFO")

    log(f"Total assets found: {len(assets)} | non-asset rows: {non_assets}", "INFO")
    return assets, non_assets


async def _delete_assets_by_macro_list(page, to_delete_set: set | None, _unused_concurrency: int = 0):

    seen = set()

    rows = await _find_rows(page)
    if not rows:
        log("[deleter] No rows found", "ERR")
        return 0

    # Build list of macro ids to delete on this subpage
    pending_macros: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            html = (await row.get_html()) or ""
        except Exception as e:
            log(f"[deleter] Failed to read row {idx}: {e}", "ERR")
            continue

        m = re.search(
            r'href="https?://[^"]*/report/macro/(\d+)/(?:show|edit|delete)"',
            html
        ) or macro_link_re.search(html)
        macro_id = m.group(1) if m else None
        if not macro_id:
            continue

        should_delete = (macro_id in to_delete_set) if to_delete_set is not None else (INCOMPLETE_AR in html)
        if should_delete and macro_id not in seen:
            pending_macros.append(macro_id)
            seen.add(macro_id)

    if not pending_macros:
        log("[deleter] nothing to delete on this subpage.", "INFO")
        return 0

    log(f"[deleter] pending macros on this subpage: {pending_macros}", "INFO")

    # Prepare all delete URLs
    delete_urls = [
        f"https://qima.taqeem.sa/report/macro/{mid}/delete"
        for mid in pending_macros
    ]
    urls_json = json.dumps(delete_urls)

    js = f"""
    (() => {{
      const urls = {urls_json};
      for (const url of urls) {{
        try {{
          const w = window.open('', '_blank');
          if (!w) continue;

          const html =
            '<!doctype html><html><head><meta charset="utf-8"><title>Deleting</title></head><body>' +
            '<script>' +
            'try{{window.alert=function(){{}};window.confirm=function(){{return true;}};window.prompt=function(){{return "";}};}}catch(e){{}}' +
            'window.addEventListener("load",function(){{setTimeout(function(){{try{{window.close();}}catch(_ ){{}}}},800);}},{{once:true}});' +
            'setTimeout(function(){{' +
            '  try{{window.location.replace(' + JSON.stringify(url) + ');}}' +
            '  catch(e){{try{{var a=document.createElement("a");a.href=' + JSON.stringify(url) + ';document.body.appendChild(a);a.click();}}catch(_ ){{}}}}' +
            '}},0);' +
            '</' + 'script>Deleting...</body></html>';

          try {{
            w.document.open();
            w.document.write(html);
            w.document.close();
          }} catch (e) {{
            try {{ w.close(); }} catch(_e) {{}}
          }}
        }} catch (e) {{
          // swallow; if one tab fails, continue with others
        }}
      }}
    }})();
    """

    try:
        await page.evaluate(js)
        log(f"[deleter] Batch delete script executed for {len(pending_macros)} assets.", "INFO")
    except Exception as e:
        # Even if evaluate fails, we log and move on; caller will rescan table
        log(f"[deleter] batch eval error (but URLs were prepared): {e}", "WARN")

    # Assume we attempted to delete all pending macros.
    deleted = len(pending_macros)
    log(f"[deleter] Total delete tabs *attempted* in batch: {deleted}/{len(pending_macros)} assets", "INFO")

    # Give the browser a little time to hit all URLs + close tabs
    await asyncio.sleep(1.5)

    return deleted


async def delete_incomplete_assets_and_leave_one(page):

        assets, non_assets = await _parse_asset_rows(page)
        if not assets:
                log("No asset rows detected.", "INFO")
                return (None, 0, False)

        # Delete ALL assets on this subpage (both complete and incomplete)
        all_ids = [a["macro_id"] for a in assets]
        total_assets = len(all_ids)
        all_assets_flag = (total_assets > 0)

        kept = None
        to_delete_set = set(all_ids)
        log(f"Deleting ALL assets on subpage: {all_ids}", "INFO")

        deleted = await _delete_assets_by_macro_list(page, to_delete_set)

        return (kept, deleted, all_assets_flag)


async def _elem_is_disabled(el) -> bool:
    """Check disabled on the element and also its parent (DataTables often disables the <li>)."""
    try:
        cls = (await el.get_attribute('class') or '').lower()
        aria = (await el.get_attribute('aria-disabled') or '').lower()
        tabindex = (await el.get_attribute('tabindex') or '')
        href = (await el.get_attribute('href') or '')
        if 'disabled' in cls:
            return True
        if aria in ('true', '1'):
            return True
        if tabindex.strip() == '-1':
            return True
        if href.strip() == '':
            return True

        # parent <li> may carry disabled state
        try:
            parent = await el.get_property('parentElement')
            if parent:
                pcls = (await parent.get_attribute('class') or '').lower()
                paria = (await parent.get_attribute('aria-disabled') or '').lower()
                if 'disabled' in pcls:
                    return True
                if paria in ('true', '1'):
                    return True
        except Exception:
            pass
    except Exception:
        pass
    return False


async def _wait_for_rows(page, timeout=8.0, poll=0.25) -> bool:
    """Wait until table rows appear or timeout."""
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        rows = await _find_rows(page)
        if rows:
            return True
        await asyncio.sleep(poll)
    log("[wait] rows did not appear in time.", "ERR")
    return False


async def _click_and_wait_table_redraw(page, button_el, timeout=6.0, poll=0.12) -> bool:
    """
    Click a pager button and wait until the table's signature changes.
    Returns True only if we detect a change; otherwise False.
    """
    try:
        loop = asyncio.get_running_loop()
        before = await _tbody_signature(page)
        await button_el.click()
        end = loop.time() + timeout
        while loop.time() < end:
            await asyncio.sleep(poll)
            after = await _tbody_signature(page)
            if after and after != before:
                return True
        return False
    except Exception as e:
        log(f"[pager] click_and_wait_table_redraw error: {e}", "ERR")
        return False


async def _datatable_prev_if_enabled(page) -> bool:
    prev_btn = await page.find(DATATABLE_PREV_SEL)
    if not prev_btn:
        return False
    if await _elem_is_disabled(prev_btn):
        return False
    try:
        changed = await _click_and_wait_table_redraw(page, prev_btn)
        if not changed:
            log("[dt-prev] click produced no redraw", "INFO")
        return changed
    except Exception as e:
        log(f"[dt-prev] click failed: {e}", "ERR")
        return False


async def _datatable_next_if_enabled(page) -> bool:
    next_btn = await page.find(DATATABLE_NEXT_SEL)
    if not next_btn:
        log("[dt-next] not found", "INFO")
        return False
    if await _elem_is_disabled(next_btn):
        log("[dt-next] disabled", "INFO")
        return False
    try:
        changed = await _click_and_wait_table_redraw(page, next_btn)
        if not changed:
            log("[dt-next] click produced no redraw", "INFO")
        return changed
    except Exception as e:
        log(f"[dt-next] click failed: {e}", "ERR")
        return False


# --- stable signature of current table body ---
async def _tbody_signature(page) -> str:
    try:
        rows = await _find_rows(page)
        if not rows:
            return "rows:0"
        parts = []
        for r in rows:
            try:
                html = (await r.get_html()) or ""
                m = macro_link_re.search(html)
                # Prefer macro id if present; otherwise a short html slice
                parts.append(m.group(1) if m else html[:40])
            except Exception:
                parts.append("err")
        return "|".join(parts)
    except Exception:
        return "sig-error"


async def _main_next_if_enabled(page) -> bool:
    """Click main paginator 'next' (rel=next) if enabled. True only if the table changed."""
    nxt = await page.find(MAIN_NEXT_SEL)
    if not nxt:
        log("[main-next] rel=next link not present; assuming last page.", "INFO")
        return False
    if await _elem_is_disabled(nxt):
        log("[main-next] disabled; reached final page.", "INFO")
        return False
    try:
        loop = asyncio.get_running_loop()
        before = await _tbody_signature(page)
        await nxt.click()
        end = loop.time() + 12.0
        while loop.time() < end:
            await asyncio.sleep(0.25)
            after = await _tbody_signature(page)
            if after and after != before:
                return True
        log("[main-next] rows didn't change signature; maybe already last page?", "INFO")
        return False
    except Exception as e:
        log(f"[main-next] click failed: {e}", "ERR")
        return False

async def _process_current_main_page_with_subpages(page):

    kept_ids = []
    deleted_total = 0

    # Ensure table is ready
    await _wait_for_rows(page, timeout=10.0)

    # Reset to subpage 1: click 'previous' until no more movement (safety cap)
    nudges = 0
    for _ in range(10):
        moved = await _datatable_prev_if_enabled(page)
        if not moved:
            break
        nudges += 1
        await _wait_for_rows(page, timeout=5.0)
    if nudges:
        log(f"[subpages] moved back {nudges} step(s) to subpage 1.", "INFO")
    else:
        log("[subpages] already at first subpage or no prev control.", "INFO")

    # Walk subpages forward: 1..N
    subpage_index = 1
    while True:
        await _wait_for_rows(page, timeout=8.0)
        kept, deleted, all_incomplete = await delete_incomplete_assets_and_leave_one(page)
        # kept is always None with new behaviour, but keep structure for compatibility
        if kept:
            kept_ids.append(kept)
        deleted_total += deleted
        log(
            f"[subpage {subpage_index}] kept={kept} deleted={deleted} all_incomplete={all_incomplete}",
            "OK"
        )

        moved = await _datatable_next_if_enabled(page)
        if not moved:
            log(f"[subpages] reached last subpage at index {subpage_index}.", "INFO")
            break

        subpage_index += 1

    return {
        "kept_ids": kept_ids,           # will usually be []
        "deleted_total": deleted_total, # total deletions on this main page
    }


# ==============================
# Orchestrator (top-level)
# ==============================



async def delete_incomplete_assets_until_delete_or_empty(page, max_rounds: int = 10):

    for round_idx in range(1, max_rounds + 1):
        log(f"[loop] Cleanup round #{round_idx}", "STEP")
        # 1) Gather all assets visible in the table and delete them
        assets, _ = await _parse_asset_rows(page)
        all_ids = [a["macro_id"] for a in assets]

        if not all_ids:
            log("[loop] No assets found in DataTable; stopping loop.", "INFO")
            return {
                "status": "NO_ASSETS",
                "rounds": round_idx,
            }

        log(f"[loop] Round #{round_idx}: deleting ALL macros: {all_ids}", "INFO")
        await _delete_assets_by_macro_list(page, set(all_ids))

        # Wait for the table to settle after the batch of deletions
        await _wait_for_rows(page, timeout=10.0)

    log(f"[loop] Reached max_rounds={max_rounds} without emptying the table.", "WARN")
    return {
        "status": "MAX_ROUNDS_REACHED",
        "rounds": max_rounds,
    }

async def delete_incomplete_assets_across_pages(page):

    total_deleted = 0
    main_pages = 0

    while True:
        main_pages += 1
        log(f"[main-page] processing page #{main_pages}", "STEP")

        # Process current main page (all DataTables subpages 1..N)
        res = await _process_current_main_page_with_subpages(page)
        deleted_here = int(res.get("deleted_total") or 0)
        total_deleted += deleted_here
        log(
            f"[main-page] page #{main_pages} deleted_total={deleted_here}, "
            f"running_total_deleted={total_deleted}",
            "INFO",
        )

        # Try to go to the next main page; if not possible, stop the crawl
        if not await _main_next_if_enabled(page):
            log("[main-page] no further main pages; stopping crawl.", "INFO")
            break

        # Wait for the table to be ready on the new main page
        await _wait_for_rows(page, timeout=10.0)

    summary = {
        "total_deleted": total_deleted,
        "main_pages_processed": main_pages,
    }
    log(f"[summary] {summary}", "OK")
    return summary

async def _has_any_assets(page) -> bool:

    try:
        has = await page.evaluate("""
        () => {
          const rows = Array.from(document.querySelectorAll('#m-table tbody tr'));
          return rows.some(tr => tr.querySelector('a[href*="/report/macro/"]'));
        }
        """)
        return bool(has)
    except Exception as e:
        log(f"[assets-check] error while checking asset rows: {e}", "ERR")
        return False

async def delete_incomplete_assets_flow(report_id: str, control_state=None, max_rounds: int = 10) -> dict:

    try:
        from scripts.core.browser.browser import new_window
        
        for round_idx in range(1, max_rounds + 1):
            log(f"Report {report_id}: cleanup round #{round_idx}", "STEP")
            
            # Open report page
            url = f"https://qima.taqeem.sa/report/{report_id}?office=487"
            log(f"Opening report: {url}", "STEP")
            page = await new_window(url)
            await asyncio.sleep(2.0)

            # Delete incomplete assets across all pages
            log(f"Report {report_id}: Deleting assets across pages…", "INFO")
            summary = await delete_incomplete_assets_across_pages(page)
            log(f"Report {report_id}: pagination summary -> {summary}", "OK")

            total_deleted = int(summary.get("total_deleted") or 0)

            if total_deleted > 0:
                # We removed at least some assets; re-open and try again next round.
                log(
                    f"Report {report_id}: Deleted {total_deleted} asset(s) in round "
                    f"#{round_idx}. Will re-open and re-check in next round.",
                    "INFO",
                )
                continue

            # total_deleted == 0 --> no assets were removed anywhere.
            log(
                f"Report {report_id}: No assets deleted in this round (total_deleted=0). Checking if any assets remain…",
                "INFO",
            )

            # Check if any assets remain
            if await _has_any_assets(page):
                # There ARE assets left that could not be deleted by this process.
                log(
                    f"Report {report_id}: Assets still exist but none were deleted. Stopping cleanup loop.",
                    "INFO",
                )
                return {
                    "status": "ASSETS_REMAIN",
                    "reportId": report_id,
                    "message": f"Assets remain but could not be deleted after {round_idx} rounds",
                    "data": summary
                }

            # No assets at all: cleanup complete
            log(f"Report {report_id}: No assets remain. Cleanup complete.", "INFO")
            return {
                "status": "SUCCESS",
                "reportId": report_id,
                "message": f"Successfully deleted all assets across {summary['main_pages_processed']} pages in {round_idx} rounds",
                "data": summary
            }

        # Reached max rounds
        log(
            f"Report {report_id}: Reached max_rounds={max_rounds} without emptying assets or stable terminal state. Manual check recommended.",
            "WARN",
        )
        return {
            "status": "MAX_ROUNDS_REACHED",
            "reportId": report_id,
            "message": f"Reached maximum rounds ({max_rounds}) without completing cleanup",
            "data": {"rounds": max_rounds}
        }

    except Exception as e:
        log(f"Error deleting incomplete assets for report {report_id}: {e}", "ERR")
        import traceback
        return {
            "status": "FAILED",
            "reportId": report_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        }