# report_actions.py
import asyncio, re, json
from .utils import log
from scripts.core.browser.browser import new_window, create_new_browser_window  # reliable new-tab open in nodriver
from .assetEdit import edit_macro_and_save

OFFICE_ID = 487

# ==============================
# Selectors / Constants
# ==============================
DELETE_REPORT_BTN = "button#delete_report.btn.btn-outline-primary"

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

# ... your other imports and helpers (like _parse_asset_rows) ...


async def create_one_asset_and_get_macro(report_id: str) -> str | None:
    """
    Create 1 asset for a report (macros = 1) and return the new macro_id.

    Steps:
      - Go to /report/asset/create/{report_id}
      - Set #macros = 1 and submit
      - Try to detect the newly created macro id:
          1) From the redirect URL if it contains /report/macro/{id}/(edit|show)
          2) Otherwise, re-open the report page and parse the assets table,
             returning the only asset (if just one exists) or the last asset.
    Returns:
      macro_id as a string, or None on failure.
    """
    create_url = f"https://qima.taqeem.sa/report/asset/create/{report_id}"
    log(f"[create-asset] Opening create page: {create_url}", "STEP")

    page = await new_window(create_url)
    await asyncio.sleep(1.0)

    # 1) Set macros = 1
    try:
        ok = await page.evaluate("""
        (() => {
            const el = document.querySelector("input#macros");
            if (!el) return false;
            el.value = "1";
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        })()
        """)
        log(f"[create-asset] set macros=1 -> ok={ok}", "INFO")
        if not ok:
            log("[create-asset] #macros input not found or not set.", "ERR")
            return None
    except Exception as e:
        log(f"[create-asset] failed to set macros=1: {e}", "ERR")
        return None

    # 2) Click Save button ("حفظ" / "Save")
    try:
        clicked = await page.evaluate("""
        (() => {
            const btns = Array.from(document.querySelectorAll("input[type=submit], button"));
            for (const b of btns) {
                const t = (b.value || b.innerText || "").trim();
                if (t.includes("حفظ") || t.toLowerCase().includes("save")) {
                    b.click();
                    return true;
                }
            }
            return false;
        })()
        """)
        log(f"[create-asset] clicked save button -> {clicked}", "INFO")
        if not clicked:
            log("[create-asset] Save button not found.", "ERR")
            return None
    except Exception as e:
        log(f"[create-asset] save click failed: {e}", "ERR")
        return None

    # Give Qima time to redirect
    await asyncio.sleep(2.0)

    # 3) Try to read macro id from current URL
    try:
        href = await page.evaluate("() => window.location.href || ''")
    except Exception:
        href = ""

    if href:
        m = re.search(r"/report/macro/(\d+)/(?:edit|show)", href)
        if m:
            macro_id = m.group(1)
            log(f"[create-asset] Detected new macro_id from URL: {macro_id}", "OK")
            return macro_id

    log("[create-asset] Could not detect macro_id from redirect URL, trying table fallback…", "WARN")

    # 4) Fallback: open report page and parse first/last asset row
    try:
        report_url = f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}"
        log(f"[create-asset] Opening report page to discover macro id: {report_url}", "INFO")
        page2 = await new_window(report_url)
        await asyncio.sleep(1.0)


        assets, _ = await _parse_asset_rows(page2)
        if not assets:
            log("[create-asset] Fallback parse: no assets found after creation.", "ERR")
            return None

        if len(assets) == 1:
            macro_id = assets[0]["macro_id"]
            log(f"[create-asset] Fallback parse: single asset macro_id={macro_id}", "OK")
            return macro_id

        # If more than one, pick the last (usually the newest)
        macro_id = assets[-1]["macro_id"]
        log(f"[create-asset] Fallback parse: chose last asset macro_id={macro_id}", "OK")
        return macro_id

    except Exception as e:
        log(f"[create-asset] error while discovering new macro id: {e}", "ERR")
        return None

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


# ==============================s
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
    For the CURRENT subpage:
      1) Scan all rows once and collect macro_ids to delete.
      2) Fire delete URLs for ALL of them in one JS evaluate() call
         (one new tab per macro, opened in a tight loop).
    We *do not* try to parse any return value from JS; we just assume
    the browser executed the script. Returns how many delete URLs we attempted.
    """
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

    # JS: loop over URLs, open one tab per URL, inject tiny HTML that
    # overrides alert/confirm/prompt and redirects to the delete URL,
    # then closes itself.
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
    """
    Delete assets with 'غير مكتملة' on the CURRENT subpage.
    NEW BEHAVIOUR:
      - Delete *all* incomplete assets.
      - Do NOT keep any incomplete asset on purpose.
    Returns (kept_macro_id_or_None, deleted_count, all_incomplete_bool).
      kept_macro_id_or_None will always be None now.
    """
    assets, non_assets = await _parse_asset_rows(page)
    if not assets:
        log("No asset rows detected.", "INFO")
        return (None, 0, False)

    incomplete_ids = [a["macro_id"] for a in assets if a["incomplete"]]
    total_assets = len(assets)
    all_incomplete = (len(incomplete_ids) == total_assets)

    log(
        f"Assets total={total_assets}, incomplete={len(incomplete_ids)}, "
        f"all_incomplete={all_incomplete}",
        "INFO"
    )

    # NEW: always delete all incomplete assets; do not intentionally keep one.
    kept = None
    to_delete = incomplete_ids
    log(f"Deleting incomplete assets only: {to_delete}", "INFO")

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
      1) Go to subpage 1 (click 'previous' until it stops changing).
      2) Walk forward through ALL DataTables subpages (1..N):
         - On each subpage, delete incomplete assets.
    Returns a dict with totals & kept ids (kept ids will be empty now).
    """
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
    """
    High-level loop for a SINGLE report page:
      - On each round:
          1) Try to click the 'Delete Report' button.
             • If it exists and click succeeds -> stop (report deleted).
          2) If button is not available:
             • Find all INCOMPLETE asset macro IDs on the current DataTable page.
             • If none found -> stop (nothing left to delete).
             • Call _delete_assets_by_macro_list(...) to fire delete URLs for all of them.
      - Repeat until either:
          • Delete Report worked, or
          • no incomplete assets remain, or
          • max_rounds is reached (safety).

    NOTE: This only works on the CURRENT visible DataTable page.
    If you have main pagination (page 1 / 2 / 3...), call this helper
    after you've navigated to whichever main page you care about.
    """
    for round_idx in range(1, max_rounds + 1):
        log(f"[loop] Cleanup round #{round_idx}", "STEP")

        # 1) Try the Delete Report button on this page
        log("[loop] Checking for Delete Report button…", "INFO")
        if await try_delete_report(page):
            log("[loop] Delete Report button clicked successfully; stopping loop.", "OK")
            return {
                "status": "DELETED",
                "rounds": round_idx,
            }

        # 2) No delete button -> delete all incomplete assets visible in the table
        assets, _ = await _parse_asset_rows(page)
        incomplete_ids = [a["macro_id"] for a in assets if a["incomplete"]]

        if not incomplete_ids:
            log("[loop] No incomplete assets found in DataTable; stopping loop.", "INFO")
            return {
                "status": "NO_INCOMPLETE_ASSETS",
                "rounds": round_idx,
            }

        log(f"[loop] Round #{round_idx}: deleting incomplete macros: {incomplete_ids}", "INFO")
        await _delete_assets_by_macro_list(page, set(incomplete_ids))

        # Wait for the table to settle after the batch of deletions
        await _wait_for_rows(page, timeout=10.0)

    log(f"[loop] Reached max_rounds={max_rounds} without delete button or empty table.", "WARN")
    return {
        "status": "MAX_ROUNDS_REACHED",
        "rounds": max_rounds,
    }

async def delete_incomplete_assets_across_pages(page):
    """
    Full crawl of the report's assets table:

      - For EACH main page:
          * Walk all DataTables subpages (1..N) and delete ALL incomplete assets
            on each subpage using delete_incomplete_assets_and_leave_one().
      - Then click main 'next' (rel="next") until it is disabled or absent.

    Returns a summary dict:

      {
        "total_deleted": int,          # total incomplete assets we attempted to delete
        "main_pages_processed": int    # how many main pages we walked
      }
    """
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
    """
    Check if there are ANY asset rows in the table (#m-table).
    We look for rows that contain a link to /report/macro/xxxx.
    """
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


async def delete_report_flow(report_id: str, template_path: str = "./asset_template.json", max_rounds: int = 10):
    """
    Main entry point - processes a single report similar to main.py.
    
    For a given report:
      Loop up to max_rounds:
        1) Open the report.
        2) Try to click the 'Delete Report' button.
           - If it works -> stop (report deletion attempted).
        3) If no Delete button:
           - Delete ALL incomplete assets across ALL main pages/subpages.
           - If we didn't delete anything this round (total_deleted == 0):
               * Re-open the report and check whether there are ANY assets left.
               * If no assets remain:
                     - Create ONE asset via create_one_asset_and_get_macro(report_id)
                     - Fill that asset with default values using edit_macro_and_save()
                     - Next loop round will re-open and try Delete again.
               * If assets remain (but no incomplete ones), stop the loop
                 (can't auto-remove complete assets).
    
    Returns a result dict with status information.
    """
    try:
        def _load_template():
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log(f"Could not load template {template_path}: {e}", "ERR")
                return {}

        total_deleted_overall = 0
        
        for round_idx in range(1, max_rounds + 1):
            log(f"Report {report_id}: cleanup round #{round_idx}", "STEP")

            # 1) Open the report page
            page = await create_new_browser_window(f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}")
            await asyncio.sleep(1.0)

            # 2) Try Delete Report button first
            log(f"Report {report_id}: checking for Delete Report button…", "INFO")
            if await try_delete_report(page):
                log(f"Report {report_id}: Delete Report button clicked in round #{round_idx}.", "OK")
                return {
                    "status": "SUCCESS",
                    "message": f"Report deleted in round {round_idx}",
                    "reportId": report_id,
                    "rounds": round_idx,
                    "deletedAssets": total_deleted_overall
                }

            # 3) No delete button -> prune incomplete assets across ALL pages/subpages
            log(
                f"Report {report_id}: Delete button not present. "
                f"Deleting incomplete assets across pages…",
                "INFO",
            )
            summary = await delete_incomplete_assets_across_pages(page)
            log(f"Report {report_id}: pagination summary -> {summary}", "OK")

            total_deleted = int(summary.get("total_deleted") or 0)
            total_deleted_overall += total_deleted

            if total_deleted > 0:
                # We removed at least some incomplete assets; re-open and try again next round.
                log(
                    f"Report {report_id}: Deleted {total_deleted} incomplete asset(s) in round "
                    f"#{round_idx}. Will re-open and re-check Delete button in next round.",
                    "INFO",
                )
                continue

            # total_deleted == 0  --> no incomplete assets were removed anywhere.
            log(
                f"Report {report_id}: No incomplete assets deleted in this round "
                f"(total_deleted=0). Checking if any assets remain…",
                "INFO",
            )

            # Re-open to check asset presence cleanly
            page2 = await page.get(f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}")
            await asyncio.sleep(1.0)
            
            if await _has_any_assets(page2):
                # There ARE assets, but none were incomplete (or deletable).
                log(
                    f"Report {report_id}: Assets still exist but none appear incomplete/deletable. "
                    f"Stopping cleanup loop.",
                    "INFO",
                )
                return {
                    "status": "PARTIAL",
                    "message": "Assets exist but none are incomplete/deletable",
                    "reportId": report_id,
                    "rounds": round_idx,
                    "deletedAssets": total_deleted_overall
                }

            # 👉 No assets at all: create ONE asset and then fill it using template
            log(f"Report {report_id}: No assets remain. Creating one new asset…", "INFO")
            macro_id = await create_one_asset_and_get_macro(report_id)
            if not macro_id:
                log(
                    f"Report {report_id}: Failed to create or detect new asset macro id. "
                    f"Stopping cleanup loop.",
                    "ERR",
                )
                return {
                    "status": "FAILED",
                    "message": "Failed to create new asset",
                    "reportId": report_id,
                    "rounds": round_idx,
                    "deletedAssets": total_deleted_overall
                }

            log(f"Report {report_id}: New asset created with macro_id={macro_id}. Filling details…", "INFO")

            values = _load_template()
            ok_fill = await edit_macro_and_save(macro_id, values)
            log(f"Report {report_id}: edit_macro_and_save(macro_id={macro_id}) -> ok={ok_fill}", "INFO")

            if not ok_fill:
                log(
                    f"Report {report_id}: Failed to fill/save the new asset macro {macro_id}. "
                    f"Stopping cleanup loop.",
                    "ERR",
                )
                return {
                    "status": "FAILED",
                    "message": f"Failed to fill/save asset {macro_id}",
                    "reportId": report_id,
                    "rounds": round_idx,
                    "deletedAssets": total_deleted_overall,
                    "macroId": macro_id
                }

            log(
                f"Report {report_id}: New asset {macro_id} created and filled. "
                f"Next round will re-open the report and try Delete button again.",
                "INFO",
            )
            # Continue to next loop round

        # Safety exit - reached max_rounds
        log(
            f"Report {report_id}: Reached max_rounds={max_rounds} without Delete Report button "
            f"appearing or stable terminal state. Manual check recommended.",
            "WARN",
        )
        return {
            "status": "MAX_ROUNDS_REACHED",
            "message": f"Reached max rounds ({max_rounds}) without completing deletion",
            "reportId": report_id,
            "rounds": max_rounds,
            "deletedAssets": total_deleted_overall
        }
        
    except Exception as e:
        log(f"Report {report_id}: Exception in delete_report_flow: {e}", "ERR")
        return {
            "status": "FAILED",
            "error": str(e),
            "reportId": report_id
        }