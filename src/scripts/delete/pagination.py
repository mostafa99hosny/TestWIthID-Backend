import asyncio
from scripts.core.browser.utils import log
from scripts.core.browser.browser import new_window

OFFICE_ID = "487"  # TODO: Move to config
MAIN_PAGER_SEL = "ul.pagination"
DATATABLE_PAGER_SEL = "#m-table_paginate"
DATATABLE_NEXT_BTN = "a.paginate_button.next#m-table_next, a.paginate_button.next[aria-controls='m-table']"

async def _click_main_go_last_numbered(page) -> bool:
    """
    In <ul class="pagination">, jump to the highest numbered page.
    If we're already on it (active span), do nothing.
    """
    js = r"""
    (() => {
      const ul = document.querySelector('ul.pagination');
      if (!ul) return { ok: false, reason: 'pagination <ul> not found' };

      const items = Array.from(ul.querySelectorAll('li.page-item'));
      if (!items.length) return { ok: false, reason: 'no <li> in pagination' };

      // Active page number (span)
      let activePage = null;
      const activeSpan = ul.querySelector('li.page-item.active span.page-link');
      if (activeSpan) {
        const t = (activeSpan.textContent || '').trim();
        if (/^\d+$/.test(t)) activePage = parseInt(t, 10);
      }

      // Collect numbered links (clickable)
      const numLinks = [];
      for (const li of items) {
        if (li.classList.contains('disabled')) continue;
        const a = li.querySelector('a.page-link');
        if (!a) continue;
        const txt = (a.textContent || '').trim();
        if (/^\d+$/.test(txt)) numLinks.push({ a, page: parseInt(txt, 10), txt, href: a.getAttribute('href') || '' });
      }

      // Also consider any numbered spans to compute true max page
      const numSpans = Array.from(ul.querySelectorAll('span.page-link'))
        .map(sp => (sp.textContent || '').trim())
        .filter(t => /^\d+$/.test(t))
        .map(t => parseInt(t, 10));

      const allPages = numLinks.map(n => n.page).concat(numSpans);
      if (!allPages.length) return { ok: false, reason: 'no numbered pages found' };

      const maxPage = Math.max(...allPages);

      // If already on the last page, don't click anything
      if (activePage !== null && activePage >= maxPage) {
        return { ok: false, reason: 'already on last page', activePage, maxPage };
      }

      // Find the link for maxPage
      const target = numLinks.find(n => n.page === maxPage);
      if (!target) {
        return { ok: false, reason: 'no link for last page (likely current is last)', activePage, maxPage };
      }

      target.a.click();
      return { ok: true, text: String(target.page), href: target.href, activePage, maxPage };
    })()
    """
    try:
        res = await page.evaluate(js)
        if isinstance(res, dict) and res.get("ok"):
            log(f"Main pager: jumped to last page (text='{res.get('text')}', href='{res.get('href')}').", "OK")
            return True
        else:
            log(f"Main pager: {res}", "INFO")
            return False
    except Exception as e:
        log(f"Main pager evaluate error: {e}", "ERR")
        return False

async def _click_datatable_go_last(page) -> bool:
    """
    DataTables sub-pager (#m-table_paginate):
    If the 'next' button is present and NOT disabled, click it once to reach page 2.
    If disabled or absent, we're already on the only page.
    """
    # Quick presence check
    try:
        exists = await page.evaluate(f"!!document.querySelector({repr(DATATABLE_PAGER_SEL)})")
        if not exists:
            log("DataTables pager not present.", "INFO")
            return False
    except Exception as e:
        log(f"DataTables presence check failed: {e}", "WARN")
        return False

    js = r"""
    (() => {
      const next = document.querySelector("a.paginate_button.next#m-table_next, a.paginate_button.next[aria-controls='m-table']");
      if (!next) return { ok: false, reason: 'next button not found' };
      const disabled = next.classList.contains('disabled') || next.getAttribute('aria-disabled') === 'true' || next.getAttribute('tabindex') === '-1';
      if (disabled) return { ok: false, reason: 'next is disabled (only one page)' };
      next.click();
      return { ok: true, moved: 'to page 2' };
    })()
    """
    try:
        res = await page.evaluate(js)
        if isinstance(res, dict) and res.get("ok"):
            log("DataTables pager: clicked Next → now on sub-page 2.", "OK")
            return True
        else:
            log(f"DataTables pager: {res}", "INFO")
            return False
    except Exception as e:
        log(f"DataTables next evaluate error: {e}", "ERR")
        return False

async def go_to_last_asset_page(report_id: str, page) -> bool:
    """
    Ensure we're viewing the last main page of the report, then, if a DataTables
    pager exists, move to sub-page 2 when available.
    
    Returns:
        bool: True if navigation occurred, False if already at last page(s)
    """
    moved = False

    # 1) Ensure we're on the correct report URL
    try:
        href = await page.evaluate("location.href")
    except Exception:
        href = ""
    expected_prefix = f"https://qima.taqeem.sa/report/{report_id}"
    if not href or expected_prefix not in href:
        url = f"https://qima.taqeem.sa/report/{report_id}?office={OFFICE_ID}"
        log(f"Re-opening report to paginate: {url}", "STEP")
        page = await new_window(url)
        await asyncio.sleep(1.2)

    # 2) Jump straight to the last numbered main page
    if await _click_main_go_last_numbered(page):
        moved = True
        await asyncio.sleep(1.2)  # allow nav to complete

    # 3) If DataTables exists, go to its last page (page 2 if Next is enabled)
    if await _click_datatable_go_last(page):
        moved = True
        await asyncio.sleep(0.8)

    if moved:
        log("Pagination: positioned at last main page and last sub-page (if present).", "OK")
    else:
        log("Pagination: already at the last page(s) or no pagination present.", "INFO")

    return moved