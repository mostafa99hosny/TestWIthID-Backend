import asyncio, json, re
from scripts.core.browser.utils import log, wait_for_element

# Normalize helpers
_ZW_RE = re.compile(r"[\u200B-\u200D\uFEFF]")

def _norm(s: str | None) -> str:
    """Normalize string by removing zero-width chars and extra whitespace"""
    if not s:
        return ""
    s = _ZW_RE.sub("", s)
    s = " ".join(s.split())
    return s.strip()

async def _eval_json(page, script: str):
    """
    Runs a JS snippet that must return JSON.stringify(obj).
    Parses and returns a Python dict/list, or None on error.
    """
    try:
        raw = await page.evaluate(script)
        if isinstance(raw, str):
            return json.loads(raw)
        # if some host returns an object, stringify via a second call
        s = await page.evaluate(f"(() => JSON.stringify(({script}) ))()")
        return json.loads(s) if isinstance(s, str) else None
    except Exception as e:
        log(f"eval error: {e}", "WARN")
        return None

async def _ensure_rows_present(page, max_wait: float = 25.0) -> bool:
    """Wait for report detail rows to appear"""
    sel = "div.d-flex.pt-sm.fs-xs, .d-flex.pt-sm.fs-xs"
    el = await wait_for_element(page, sel, timeout=max_wait)
    return el is not None

async def extract_report_info(page, timeout: float = 30.0, interval: float = 0.5) -> dict:
    """
    Deep-scan for report rows across top document, shadow DOM, and same-origin iframes.
    
    Returns:
        dict: {
            "found": bool,
            "rows": [{"label": str, "value": str, "href": str}, ...],
            "by_label": {label: {"value": str, "href": str}},
            "alias": {
                "status": {"value": str, "href": str},
                "issue_date": {...},
                ...
            },
            "meta": {...}
        }
    """
    ok = await _ensure_rows_present(page, max_wait=timeout)
    if not ok:
        log("No candidate rows appeared in time.", "ERR")
        return {"found": False, "rows": [], "by_label": {}, "alias": {}, "meta": {}}

    js_collect = r"""
    (() => {
      function collectFromNode(root) {
        const out = [];
        if (!root) return out;

        const nodes = root.querySelectorAll('div.d-flex.pt-sm.fs-xs, .d-flex.pt-sm.fs-xs');
        for (const n of nodes) {
          const span = n.querySelector('span');
          const b = n.querySelector('b');
          const a = n.querySelector('a');
          const label = (span && span.textContent ? span.textContent : "").trim();
          const value = (b && b.textContent ? b.textContent : "").trim();
          const href  = a ? (a.getAttribute('href') || "").trim() : "";
          if (label || value || href) out.push({ label, value, href });
        }

        // Shadow roots
        const stack = [];
        function pushShadowHosts(nodeList) {
          for (const el of nodeList) {
            if (el && el.shadowRoot) stack.push(el.shadowRoot);
          }
        }
        pushShadowHosts(root.querySelectorAll('*'));
        while (stack.length) {
          const sr = stack.pop();
          const nodes2 = sr.querySelectorAll('div.d-flex.pt-sm.fs-xs, .d-flex.pt-sm.fs-xs');
          for (const n of nodes2) {
            const span = n.querySelector('span');
            const b = n.querySelector('b');
            const a = n.querySelector('a');
            const label = (span && span.textContent ? span.textContent : "").trim();
            const value = (b && b.textContent ? b.textContent : "").trim();
            const href  = a ? (a.getAttribute('href') || "").trim() : "";
            if (label || value || href) out.push({ label, value, href });
          }
          pushShadowHosts(sr.querySelectorAll('*'));
        }

        return out;
      }

      // Top document
      let rows = collectFromNode(document);

      // Same-origin iframes
      const iframes = Array.from(document.querySelectorAll('iframe'));
      let iframeCount = 0, iframeMatches = 0;
      for (let i = 0; i < iframes.length; i++) {
        const f = iframes[i];
        try {
          const d = f.contentDocument || f.contentWindow?.document;
          if (!d) continue;
          iframeCount++;
          const got = collectFromNode(d);
          iframeMatches += got.length;
          if (got && got.length) rows.push(...got);
        } catch (e) { /* cross-origin */ }
      }

      const by_label = {};
      for (const r of rows) {
        if (r.label) by_label[r.label] = { value: r.value, href: r.href };
      }

      const payload = {
        found: rows.length > 0,
        count: rows.length,
        rows,
        by_label,
        meta: {
          href: location.href,
          readyState: document.readyState,
          iframes: iframes.length,
          iframeMatches
        }
      };
      return JSON.stringify(payload);
    })()
    """

    elapsed = 0.0
    last_raw = None
    while elapsed < timeout:
        raw = await _eval_json(page, js_collect)
        last_raw = raw
        if raw and isinstance(raw, dict) and raw.get("found") and raw.get("rows"):
            break
        await asyncio.sleep(interval)
        elapsed += interval

    if not last_raw or not last_raw.get("found"):
        log("Report info not found after deep scan.", "ERR")
        return {"found": False, "rows": [], "by_label": {}, "alias": {}, "meta": last_raw or {}}

    # Normalize rows
    rows = [{
        "label": _norm(r.get("label")),
        "value": _norm(r.get("value")),
        "href":  (r.get("href") or "")
    } for r in last_raw.get("rows", [])]

    by_label = {}
    for r in rows:
        if r["label"]:
            by_label[r["label"]] = {"value": r["value"], "href": r["href"]}

    def pick(lbls):
        """Pick first matching label from list"""
        for L in lbls:
            if L in by_label:
                return by_label[L]
        return None

    # Create convenient aliases for common fields
    alias = {
        "status": pick(["حالة التقرير:", "حالة التقرير", "Report Status:", "Report Status"]),
        "issue_date": pick(["تاريخ إصدار التقرير:", "تاريخ إصدار التقرير", "Report Issue Date"]),
        "assumptions": pick(["الافتراضات:", "الافتراضات"]),
        "special_assumptions": pick(["الافتراضات الخاصة:", "الافتراضات الخاصة"]),
        "final_value": pick(["الرأي النهائي في القيمة:", "الرأي النهائي في القيمة", "Final Opinion of Value"]),
        "original_report_file": pick(["ملف أصل التقرير:", "ملف أصل التقرير"]),
        "purpose": pick(["الغرض من التقييم:", "الغرض من التقييم", "Purpose of Valuation"]),
        "report_type": pick(["نوع التقرير:", "نوع التقرير", "Report Type"]),
        "valuation_date": pick(["تاريخ التقييم:", "تاريخ التقييم", "Valuation Date"]),
    }

    # Log preview of found data
    preview = [{
        "label": r["label"],
        "value": r["value"][:80],
        **({"href": r["href"]} if r["href"] else {})
    } for r in rows[:12]]
    meta = last_raw.get("meta") or {}
    log("Report rows (sample): " + json.dumps(preview, ensure_ascii=False), "INFO")
    log("Report meta: " + json.dumps(meta, ensure_ascii=False), "INFO")

    return {"found": True, "rows": rows, "by_label": by_label, "alias": alias, "meta": meta}