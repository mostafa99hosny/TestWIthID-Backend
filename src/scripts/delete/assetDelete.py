import asyncio, json
from scripts.core.browser.utils import log
from scripts.core.browser.browser import new_window
from .pagination import go_to_last_asset_page

async def _eval_json(page, script: str):
    """Evaluate JS that returns JSON.stringify(...) and parse it"""
    try:
        raw = await page.evaluate(script)
        if isinstance(raw, str):
            return json.loads(raw)
    except Exception as e:
        log(f"eval error: {e}", "WARN")
    return None

async def _get_last_asset_id(page) -> str | None:
    """
    From the current page (already on last main/sub page), read #m-table,
    pick the LAST <tr> in <tbody>, parse the first <td> link href, and extract the macro id.
    Supports top document and same-origin iframes.
    """
    js = r"""
    (() => {
      function lastIdFrom(doc) {
        const tbl = doc.querySelector('#m-table');
        if (!tbl) return null;
        const rows = tbl.querySelectorAll('tbody tr');
        if (!rows || rows.length === 0) return null;
        const last = rows[rows.length - 1];
        const firstCellLink = last.querySelector('td a[href*="/report/macro/"]');
        if (!firstCellLink) return null;
        const href = firstCellLink.getAttribute('href') || '';
        const m = href.match(/\/report\/macro\/(\d+)\//);
        return m ? m[1] : null;
      }

      // Try top doc
      let id = lastIdFrom(document);
      if (id) return JSON.stringify({ where: "top", id });

      // Try same-origin iframes
      const ifr = Array.from(document.querySelectorAll('iframe'));
      for (let i = 0; i < ifr.length; i++) {
        try {
          const d = ifr[i].contentDocument || ifr[i].contentWindow?.document;
          if (!d) continue;
          id = lastIdFrom(d);
          if (id) return JSON.stringify({ where: "iframe", index: i, id });
        } catch (e) {}
      }
      return JSON.stringify(null);
    })()
    """
    res = await _eval_json(page, js)
    if res and isinstance(res, dict):
        where = res.get("where")
        mid = res.get("id")
        if mid:
            log(f"Last asset macro id found in {where}: {mid}", "OK")
            return mid
    return None

async def delete_latest_asset(report_id: str, page) -> bool:
    """
    Delete the most recently created asset (assumes it's on the last page).
    
    Steps:
    1. Navigate to last main page + last sub page
    2. Read #m-table last row macro id
    3. Open /report/macro/{id}/delete
    
    Returns:
        bool: True if delete was attempted, False if asset not found
    """
    try:
        await go_to_last_asset_page(report_id, page)
    except Exception as e:
        log(f"Pagination step failed (continuing anyway): {e}", "WARN")

    # Scroll to encourage lazy content to render
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    await asyncio.sleep(0.4)

    # Get the macro ID of the last asset
    macro_id = await _get_last_asset_id(page)
    if not macro_id:
        log("Could not read last asset macro id from #m-table.", "ERR")
        return False

    # Open the delete URL
    delete_url = f"https://qima.taqeem.sa/report/macro/{macro_id}/delete"
    log(f"Opening delete URL: {delete_url}", "STEP")
    del_page = await new_window(delete_url)
    await asyncio.sleep(0.8)

    log(f"Delete attempted for macro {macro_id}.", "OK")
    return True