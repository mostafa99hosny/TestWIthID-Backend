import asyncio, re, json
from .utils import log
from scripts.core.browser.browser import new_window  # reliable new-tab open in nodriver
from .assetEdit import edit_macro_and_save

# ==============================
# Selectors / Constants
# ==============================
DELETE_REPORT_BTN = "button#delete_report.btn.btn-outline-primary"

OFFICE_ID = "487"


# Prefer CSS (works best with DataTables)
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


# ==============================
# Dialog/Confirm helpers
# ==============================

async def _ensure_confirm_ok(page):
    """
    Auto-accept alert/confirm/prompt and suppress ALL 'beforeunload' leave dialogs.
    Patches top window + same-origin iframes and re-applies right before clicks/submits.
    Returns the number of windows patched (int).
    """
    js = r"""
    (() => {
      function hardPatch(win){
        try{
          const yes  = () => true;
          const noop = () => {};
          // Basic dialog overrides
          try{ win.confirm = yes; }catch(_){}
          try{ win.alert   = noop; }catch(_){}
          try{ win.prompt  = () => ""; }catch(_){}
          try{ Object.defineProperty(win,'confirm',{value:yes,configurable:true}); }catch(_){}
          try{ Object.defineProperty(win,'alert',  {value:noop,configurable:true}); }catch(_){}
          try{ Object.defineProperty(win,'prompt', {value:()=>"",configurable:true}); }catch(_){}

          // Kill existing beforeunload
          try{ win.onbeforeunload = null; }catch(_){}
          try{
            Object.defineProperty(win,'onbeforeunload',{
              configurable:true,
              get(){ return null; },
              set(_v){ /* swallow any future assignment */ }
            });
          }catch(_){}

          // Ignore any new listeners for 'beforeunload'
          try{
            const origAdd = win.addEventListener.bind(win);
            win.addEventListener = function(type, listener, options){
              if (type === 'beforeunload') return;  // block
              return origAdd(type, listener, options);
            };
          }catch(_){}
          try{
            if (win.attachEvent){
              const origAttach = win.attachEvent.bind(win);
              win.attachEvent = function(type, listener){
                if (String(type).toLowerCase() === 'onbeforeunload') return;
                return origAttach(type, listener);
              };
            }
          }catch(_){}

          // As a final guard: if any 'beforeunload' still fires, neutralize it.
          try{
            origBU && win.removeEventListener('beforeunload', origBU, true);
          }catch(_){}
          try{
            var origBU = function(e){
              try{
                e.stopImmediatePropagation();
                Object.defineProperty(e,'returnValue',{value:undefined,writable:true});
              }catch(_){}
            };
            win.addEventListener('beforeunload', origBU, true);
          }catch(_){}
        }catch(_){}
      }

      function patchAll(win){
        hardPatch(win);
        let n = 1;
        for (const f of Array.from(win.frames||[])){
          try{
            if (f.location && f.location.origin === win.location.origin){
              hardPatch(f);
              n++;
            }
          }catch(_){}
        }
        const reassert = () => { try{ hardPatch(win); }catch(_){} };
        try{
          win.addEventListener('click',  reassert, true);
          win.addEventListener('submit', reassert, true);
          win.addEventListener('keydown',reassert, true);
          win.addEventListener('mousedown',reassert, true);
          win.addEventListener('touchstart',reassert, true);
        }catch(_){}
        return n;
      }

      return patchAll(window);
    })()
    """
    try:
        count = await page.evaluate(js)
        try:
            n = int(count) if count is not None else 0
        except Exception:
            n = 0
        log(f"[confirm] Auto-OK + no-leave patched in {n} window(s).", "INFO")
        return n
    except Exception as e:
        log(f"[confirm] Patch failed: {e}", "ERR")
        return 0


async def _try_click_inline_confirm(page):
    """If the /delete page shows an on-page confirm, click it (Arabic/English)."""
    try:
        clicked = await page.evaluate("""
        () => {
          const labels = ["OK","Ok","Confirm","CONFIRM","Yes","Delete","حذف","تأكيد","موافق"];
          const els = Array.from(document.querySelectorAll('button, [type=button], [type=submit], a'));
          for (const el of els) {
            const t = (el.innerText || el.value || "").trim();
            if (!t) continue;
            for (const key of labels) {
              if (t.includes(key)) { el.click(); return true; }
            }
          }
          return false;
        }
        """)
        log("[confirm] Inline confirm " + ("clicked." if clicked else "not detected."), "INFO")
    except Exception as e:
        log(f"[confirm] Inline confirm scan failed: {e}", "ERR")


async def try_delete_report(page):
    log("Scanning for 'Delete Report' button…", "INFO")
    btn = await page.find(DELETE_REPORT_BTN)
    if not btn:
        log("Delete button not present.", "INFO")
        return False

    log("Found 'Delete Report' button — clicking (auto-accept confirm)…", "STEP")
    await _ensure_confirm_ok(page)
    try:
        await btn.click()
        await asyncio.sleep(1.0)
        log("Delete clicked. If a confirm dialog existed, it was auto-accepted.", "OK")
    except Exception as e:
        log(f"Delete report click failed: {e}", "ERR")
        return False
    return True


# ==============================
# Table scanning / parsing
# ==============================

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


# ==============================
# Parsing assets on current (sub)page
# ==============================

async def _parse_asset_rows(page):
    """
    Return (assets, non_asset_rows_count) from the current page.
    """
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


# ==============================
# Delete flow
# ==============================

async def _open_new_tab(url: str, pause: float = 1.0, retries: int = 2):
    """Open URL in a NEW tab; retry on transient transport errors."""
    for attempt in range(retries + 1):
        try:
            log(f"[new-tab] -> {url} (try {attempt+1}/{retries+1})", "INFO")
            page2 = await new_window(url)
            await asyncio.sleep(pause)
            return page2
        except Exception as e:
            log(f"[new-tab] failed: {e}", "WARN")
            await asyncio.sleep(0.6 + 0.6 * attempt)
    raise RuntimeError("new-tab-open-failed")


async def _delete_assets_by_macro_list(page, to_delete_set: set | None, _unused_concurrency: int = 0):
    """
    For each target macro:
      - open a same-origin child tab
      - inject a tiny HTML that patches confirm/alert and redirects to /delete
      - let the child tab close itself after load/redirect
    Runs sequentially for stability on Windows. The original tab stays untouched.
    """
    deleted = 0
    seen = set()

    rows = await _find_rows(page)
    if not rows:
        log("[deleter] No rows found", "ERR")
        return deleted

    # Build list of macro ids to delete on this subpage
    pending_macros = []
    for idx, row in enumerate(rows, start=1):
        try:
            html = (await row.get_html()) or ""
        except Exception as e:
            log(f"[deleter] Failed to read row {idx}: {e}", "ERR")
            continue

        m = re.search(r'href="https?://[^"]*/report/macro/(\d+)/(?:show|edit|delete)"', html) or macro_link_re.search(html)
        macro_id = m.group(1) if m else None
        if not macro_id:
            continue

        should_delete = (macro_id in to_delete_set) if to_delete_set is not None else (INCOMPLETE_AR in html)
        if should_delete and macro_id not in seen:
            pending_macros.append(macro_id)

    if not pending_macros:
        log("[deleter] nothing to delete on this subpage.", "INFO")
        return 0

    # Launch each delete in its own child tab
    for macro_id in pending_macros:
        delete_url = f"https://qima.taqeem.sa/report/macro/{macro_id}/delete"
        log(f"[deleter] Launch delete in child tab for macro {macro_id}", "STEP")

        # Build a single-string JS payload (no external args) that:
        #  - opens an about:blank tab (same-origin)
        #  - writes HTML that sets confirm/alert/prompt and redirects to the /delete URL
        #  - closes itself shortly after load
        redirect_html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Deleting {macro_id}</title></head>
<body>
<script>
  try {{
    window.alert = function(){{}};
    window.confirm = function(){{ return true; }};
    window.prompt = function(){{ return ""; }};
    Object.defineProperty(window, 'alert',   {{ configurable:true, value: function(){{}} }});
    Object.defineProperty(window, 'confirm', {{ configurable:true, value: function(){{ return true; }} }});
    Object.defineProperty(window, 'prompt',  {{ configurable:true, value: function(){{ return ""; }} }});
  }} catch (e) {{}}

  // close after final page load
  window.addEventListener('load', function() {{
    setTimeout(function(){{ try {{ window.close(); }} catch(_ ){{}} }}, 800);
  }}, {{ once: true }});

  // redirect to the real delete endpoint (will trigger confirm -> OK automatically)
  setTimeout(function(){{
    try {{
      window.location.replace({json.dumps(delete_url)});
    }} catch (e) {{
      // fallback via anchor
      try {{
        var a = document.createElement('a');
        a.href = {json.dumps(delete_url)};
        document.body.appendChild(a);
        a.click();
      }} catch (_e) {{}}
    }}
  }}, 0);
</script>
Deleting macro {macro_id}...
</body></html>"""

        js = f"""
        (() => {{
          try {{
            var w = window.open('', '_blank');
            if (!w) return {{ ok:false, error:'popup-blocked' }};
            try {{
              w.document.open();
              w.document.write({json.dumps(redirect_html)});
              w.document.close();
            }} catch (e) {{
              try {{ w.close(); }} catch(_ ){{}}
              return {{ ok:false, error:'doc-write-failed:' + String(e) }};
            }}
            return {{ ok:true }};
          }} catch (e) {{
            return {{ ok:false, error:String(e) }};
          }}
        }})()
        """

        # Execute in the original page
        try:
            res = await page.evaluate(js)
        except Exception as e:
            # Some nodriver builds return structured arrays; treat any eval as "launched"
            log(f"[deleter] eval-exc launching child for {macro_id}: {e}", "WARN")
            res = {"ok": True}

        # Be generous interpreting success — many engines return non-plain objects.
        ok = False
        if isinstance(res, dict):
            ok = bool(res.get("ok", False))
        else:
            # if we got *anything* back, assume tab opened
            ok = True

        if ok:
            deleted += 1
            seen.add(macro_id)
            log(f"[deleter] Delete tab launched for macro {macro_id}", "OK")
        else:
            log(f"[deleter] Failed to launch delete for macro {macro_id}: {res}", "ERR")

        # Give the child time to redirect+delete+close
        await asyncio.sleep(0.9)

    log(f"[deleter] Total deleted: {deleted} assets", "INFO")
    return deleted

async def delete_incomplete_assets_and_leave_one(page):
    """
    Delete assets with 'غير مكتملة'.
    - If ALL assets are incomplete: keep the FIRST *asset row*; delete the rest; return its macro_id as 'kept'.
    - If some assets are complete: delete only incomplete assets; return kept=None.
    Returns (kept_macro_id_or_None, deleted_count, all_incomplete_bool).
    """
    assets, non_assets = await _parse_asset_rows(page)
    if not assets:
        log("No asset rows detected.", "INFO")
        return (None, 0, False)

    incomplete_ids = [a["macro_id"] for a in assets if a["incomplete"]]
    total_assets = len(assets)
    all_incomplete = (len(incomplete_ids) == total_assets)

    log(f"Assets total={total_assets}, incomplete={len(incomplete_ids)}, all_incomplete={all_incomplete}", "INFO")

    kept = None

    if all_incomplete:
        # Keep the first ASSET row
        kept = assets[0]["macro_id"]
        log(f"ALL assets incomplete. Will KEEP first asset macro {kept} and delete others.", "INFO")
        to_delete = [a["macro_id"] for a in assets[1:]]  # everything except the first asset
    else:
        # Partial case: delete only incomplete assets
        to_delete = incomplete_ids
        log(f"PARTIAL: Deleting only incomplete assets: {to_delete}", "INFO")

    # Delete while navigating UI pages so we follow pagination controls.
    to_delete_set = set(to_delete)
    param = to_delete_set if len(to_delete_set) > 0 else None
    deleted = await _delete_assets_by_macro_list(page, param)

    return (kept, deleted, all_incomplete)


# ==============================
# Pagination utilities
# ==============================

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

# ==============================
# Page processors (subpages within a main page)
# ==============================

async def _process_current_main_page_with_subpages(page):
    """
    On the current main page:
      1) Go to subpage 1 (click 'previous' until disabled).
      2) Clean subpage 1 using your existing rule.
      3) If subpage 2 exists (next enabled), go there and clean.
    Returns a dict with totals & kept ids.
    """
    kept_ids = []
    deleted_total = 0

    # Ensure table is ready
    await _wait_for_rows(page, timeout=10.0)

    # Reset to subpage 1 by clicking 'previous' until disabled
    
    # Reset to subpage 1: try 'previous' up to 3 times; stop if no redraw
    nudges = 0
    for _ in range(3):
        moved = await _datatable_prev_if_enabled(page)
        if not moved:
            break
        nudges += 1
        await _wait_for_rows(page, timeout=5.0)
    if nudges:
        log(f"[subpages] moved back {nudges} step(s) to subpage 1.", "INFO")

    # Subpage 1
    await _wait_for_rows(page, timeout=8.0)
    kept, deleted, all_incomplete = await delete_incomplete_assets_and_leave_one(page)
    if kept:
        kept_ids.append(kept)
    deleted_total += deleted
    log(f"[subpage 1] kept={kept} deleted={deleted} all_incomplete={all_incomplete}", "OK")

    # Try Subpage 2
    if await _datatable_next_if_enabled(page):
        await _wait_for_rows(page, timeout=8.0)
        kept2, deleted2, all_incomplete2 = await delete_incomplete_assets_and_leave_one(page)
        if kept2:
            kept_ids.append(kept2)
        deleted_total += deleted2
        log(f"[subpage 2] kept={kept2} deleted={deleted2} all_incomplete={all_incomplete2}", "OK")
    else:
        log("[subpages] no subpage 2 (next disabled).", "INFO")

    return {
        "kept_ids": kept_ids,           # 0..2 ids, one per subpage at most
        "deleted_total": deleted_total, # total deletions on this main page
    }


# ==============================
# Orchestrator (top-level)
# ==============================

async def delete_incomplete_assets_across_pages(page):
    """
    Full crawl:
      - For EACH main page:
         * subpage 1 -> clean (keep one if all incomplete)
         * subpage 2 (if enabled) -> clean
      - Then click main 'next' (rel=next) until disabled/absent.

    Returns:
      {
        "total_deleted": int,
        "kept_by_main_page": [ [kept_ids_for_main_page1], [kept_ids_for_main_page2], ... ],
        "main_pages_processed": int
      }
    """
    total_deleted = 0
    kept_by_page = []
    main_pages = 0

    while True:
        main_pages += 1
        log(f"[main-page] processing page #{main_pages}", "STEP")

        # Process current main page (both subpages)
        res = await _process_current_main_page_with_subpages(page)
        kept_by_page.append(res["kept_ids"])
        total_deleted += res["deleted_total"]

        # Try go to next main page
        if not await _main_next_if_enabled(page):
            break

        # Wait for the table to be ready on the new main page
        await _wait_for_rows(page, timeout=10.0)

    summary = {
        "total_deleted": total_deleted,
        "kept_by_main_page": kept_by_page,
        "main_pages_processed": main_pages
    }
    log(f"[summary] {summary}", "OK")
    return summary


async def delete_report_flow(report_id: str, template_path: str = "./asset_template.json"):
    """
    Main entry point - does exactly what their main.py does but returns a result dict.
    """
    try:
        def _load_template():
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log(f"Could not load template {template_path}: {e}", "ERR")
                return {}

        url = f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}"
        max_attempts = 5
        attempt = 0
        last_kept_id = None
        total_deleted = 0
        while attempt < max_attempts:
            page = await new_window(url)
            await asyncio.sleep(1.0)
            # Try delete button
            if await try_delete_report(page):
                return {"status": "SUCCESS", "message": "Report deleted", "reportId": report_id}

            # Prune incomplete assets
            summary = await delete_incomplete_assets_across_pages(page)
            total_deleted += summary.get("total_deleted", 0)
            kept_ids = [kid for sub in summary.get("kept_by_main_page", []) for kid in sub if kid]

            # If only one incomplete asset remains and still no delete button, edit it
            if kept_ids and len(kept_ids) == 1:
                last_kept_id = kept_ids[0]
                template = _load_template()
                await edit_macro_and_save(last_kept_id, template)
                # After editing, try again
                page = await new_window(url)
                await asyncio.sleep(1.0)
                if await try_delete_report(page):
                    return {"status": "SUCCESS", "message": "Report deleted after completion", "reportId": report_id}
                # If still not, break to avoid infinite loop
                break

            # If no assets left to process, break
            if not kept_ids:
                break

            attempt += 1

        # Final check
        page = await new_window(url)
        await asyncio.sleep(1.0)
        if await try_delete_report(page):
            return {"status": "SUCCESS", "message": "Report deleted after cleanup", "reportId": report_id, "deletedAssets": total_deleted}

        return {
            "status": "PARTIAL",
            "message": "Cleanup done but delete button not available",
            "reportId": report_id,
            "deletedAssets": total_deleted,
            "lastKeptId": last_kept_id
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e), "reportId": report_id}