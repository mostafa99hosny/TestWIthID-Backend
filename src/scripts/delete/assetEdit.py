import asyncio
import json
from .utils import log, wait_for_element
from scripts.core.browser.browser import new_window

# ---------- helpers ----------

def _js(val):
    """Embed Python value in JS safely for page.evaluate IIFEs (no args)."""
    return json.dumps(val, ensure_ascii=False)

async def _set_input_value_by_id(page, el_id: str, value):
    code = f"""
    (() => {{
      const id = {_js(el_id)};
      const val = {_js(str(value))};
      const el = document.getElementById(id);
      if (!el) return false;
      try {{ el.focus(); }} catch(_){{}}
      el.value = val;
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return true;
    }})()
    """
    ok = await page.evaluate(code)
    return bool(ok)

async def _set_select_value_by_id(page, el_id: str, value):
    # JS boolean must be lowercase 'false'
    code = f"""
    (() => {{
      const id = {_js(el_id)};
      const val = {_js(str(value))};
      const el = document.getElementById(id);
      if (!el) return false;
      let found = false;
      for (const opt of Array.from(el.options || [])) {{
        if (String(opt.value) == String(val)) {{ opt.selected = true; found = true; break; }}
      }}
      if (!found) el.value = val;
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return true;
    }})()
    """
    ok = await page.evaluate(code)
    return bool(ok)

# ---------- Select2 UNDERLYING <select> helpers (hard-coded path) ----------

async def _set_underlying_select(page, select_css: str, value: str) -> bool:
    """Set hidden <select> value and trigger change; prefer jQuery/Select2 when present."""
    args = json.dumps({"css": select_css, "value": str(value)}, ensure_ascii=False)
    res = await page.evaluate(f"""
    (() => {{
      const args = {args};
      const el = document.querySelector(args.css);
      if (!el) return "no-select";
      const $ = window.jQuery || window.$;
      try {{
        if ($ && $.fn && $.fn.select2) {{
          $(el).val(String(args.value)).trigger('change');
        }} else {{
          el.value = String(args.value);
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        return "ok";
      }} catch(e) {{
        try {{
          el.value = String(args.value);
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          el.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return "ok-fallback";
        }} catch(e2) {{
          return "error";
        }}
      }}
    }})()
    """)
    log(f"[loc:set] {select_css} <- {value} => {res}", "INFO")
    return res in ("ok", "ok-fallback")

async def _sync_select2_container_text(page, select_css: str) -> None:
    """Fallback: update Select2 visible label text/title to selected option."""
    await page.evaluate(f"""
    (() => {{
      const sel = document.querySelector({json.dumps(select_css)});
      if (!sel || !sel.id) return;
      const opt = sel.options && sel.options[sel.selectedIndex || 0];
      const txt = (opt && (opt.textContent || opt.innerText || '')).trim();
      const cid = 'select2-' + sel.id + '-container';
      const c = document.getElementById(cid);
      if (c && txt) {{
        c.textContent = txt;
        c.setAttribute('title', txt);
      }}
    }})()
    """)

async def _count_select_options(page, select_css: str) -> int:
    return int(await page.evaluate(f"""
    (() => {{
      const el = document.querySelector({json.dumps(select_css)});
      if (!el || !el.options) return 0;
      return el.options.length;
    }})()
    """) or 0)

async def _wait_select_has_options(page, select_css: str, min_count: int = 2, timeout: float = 12.0) -> bool:
    """Wait until a <select> has at least min_count options (after parent change)."""
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        count = await _count_select_options(page, select_css)
        if count >= min_count:
            log(f"[loc:wait] {select_css} options={count} (>= {min_count})", "INFO")
            return True
        await asyncio.sleep(0.4)
    log(f"[loc:wait] timeout waiting options for {select_css}", "WARN")
    return False

async def _verify_select2_non_placeholder(page, container_css: str) -> bool:
    """Check visible Select2 container is not 'Select'/'تحديد' or empty."""
    ok = await page.evaluate(f"""
    (() => {{
      const el = document.querySelector({json.dumps(container_css)});
      if (!el) return false;
      const txt = (el.getAttribute('title') || el.textContent || '').trim();
      return !!txt && !['Select','تحديد','-- اختر --',''].includes(txt);
    }})()
    """)
    log(f"[loc:verify] {container_css} -> {ok}", "INFO")
    return bool(ok)

# ---------- Submit & wait ----------

async def _submit_via_save(page):
    """
    Find #save button, submit the owning form using requestSubmit/submit.
    Return one of: 'requestSubmit', 'submit', 'clicked-noform', 'no-btn'
    """
    code = """
    (() => {
      const btn =
        document.querySelector("input#save[name='update']") ||
        document.querySelector("input#save") ||
        document.querySelector("input[type='submit'][name='update']") ||
        document.querySelector("button#save[name='update']") ||
        document.querySelector("button[type='submit']");
      if (!btn) return "no-btn";
      const form = btn.form || btn.closest('form');
      if (form) {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit(btn);
          return "requestSubmit";
        }
        form.submit();
        return "submit";
      } else {
        btn.click();
        return "clicked-noform";
      }
    })()
    """
    mode = await page.evaluate(code)
    log(f"[save] submit mode: {mode}", "INFO")
    return mode

async def _wait_post_save(page, macro_id: str, timeout=12):
    """
    Wait until we navigate away from the edit page or see a likely success marker.
    """
    edit_suffix = f"/report/macro/{macro_id}/edit"

    async def _href():
        try:
            return await page.evaluate("() => window.location.href")
        except Exception:
            return ""

    async def _has_success_flash():
        try:
            return await page.evaluate("""
              () => !!(
                document.querySelector('.alert-success, .text-success') ||
                Array.from(document.querySelectorAll('*')).some(n => /تم|حفظ|Saved|success/i.test(n.textContent||""))
              )
            """)
        except Exception:
            return False

    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        href = (await _href()) or ""
        if edit_suffix not in href:
            log(f"[save-wait] navigated away from edit -> {href}", "INFO")
            return True
        if await _has_success_flash():
            log("[save-wait] success flash detected (still on edit URL).", "INFO")
            return True
        await asyncio.sleep(0.5)
    log("[save-wait] timeout waiting for post-save transition.", "ERR")
    return False

# ---------- Location (HARD-CODED C/R/C = "1") ----------

async def _find_option_value_by_labels(page, select_css: str, labels: list[str]):
    labels = [s for s in labels if s]
    if not labels:
        return None
    args = json.dumps({"css": select_css, "labels": labels}, ensure_ascii=False)
    return await page.evaluate(f"""
    (() => {{
      const args = {args};
      const el = document.querySelector(args.css);
      if (!el || !el.options) return null;
      const want = args.labels.map(s => String(s).trim().toLowerCase());
      for (const opt of Array.from(el.options)) {{
        const t = (opt.textContent || opt.innerText || '').trim().toLowerCase();
        if (want.includes(t)) return String(opt.value ?? '');
      }}
      // also allow substring match if exact not found
      for (const opt of Array.from(el.options)) {{
        const t = (opt.textContent || opt.innerText || '').trim().toLowerCase();
        if (want.some(w => t.includes(w))) return String(opt.value ?? '');
      }}
      return null;
    }})()
    """)

async def _first_valid_option_value(page, select_css: str):
    return await page.evaluate(f"""
    (() => {{
      const el = document.querySelector({json.dumps(select_css)});
      if (!el || !el.options) return null;
      for (const opt of Array.from(el.options)) {{
        const v = String(opt.value ?? '');
        if (v && v !== '0') return v;
      }}
      return null;
    }})()
    """)

async def _get_value(page, select_css: str) -> str | None:
    return await page.evaluate(f"""
    (() => {{
      const el = document.querySelector({json.dumps(select_css)});
      return el ? String(el.value ?? '') : null;
    }})()
    """)

async def set_location_select2s(page, values: dict) -> None:
    """
    Country=1 (Saudi Arabia), Region=1 (Riyadh Province), City resolved by label
    ('Riyadh'/'الرياض') or first valid city under the selected region.
    Keeps Select2 UI in sync and re-asserts region after city set.
    """
    # 1) Country = 1
    ok_country = await _set_underlying_select(page, "#country_id", "1")
    await _wait_select_has_options(page, "#region", min_count=2, timeout=15)
    await asyncio.sleep(0.3)
    v_country = await _verify_select2_non_placeholder(page, "span#select2-country_id-container")
    if not v_country:
        await _sync_select2_container_text(page, "#country_id")

    # 2) Region = 1 (Riyadh Province)
    ok_region = await _set_underlying_select(page, "#region", "1")
    await _wait_select_has_options(page, "#city", min_count=2, timeout=15)
    await asyncio.sleep(0.3)
    v_region = await _verify_select2_non_placeholder(page, "span#select2-region-container")
    if not v_region:
        await _sync_select2_container_text(page, "#region")

    # 3) City — resolve a value that belongs to Region=1
    city_label_candidates = []
    # take provided labels first if present
    if values.get("city_label"):
        city_label_candidates.append(values["city_label"])
    city_label_candidates += values.get("city_label_alts", [])
    # sensible defaults for Riyadh
    city_label_candidates += ["Riyadh", "الرياض"]

    city_val = await _find_option_value_by_labels(page, "#city", city_label_candidates)
    if not city_val:
        city_val = await _first_valid_option_value(page, "#city")

    ok_city = False
    if city_val:
        ok_city = await _set_underlying_select(page, "#city", city_val)
        await asyncio.sleep(0.3)
        v_city = await _verify_select2_non_placeholder(page, "span#select2-city-container")
        if not v_city:
            await _sync_select2_container_text(page, "#city")

    # 4) Re-assert region (some UIs auto-adjust it after city change)
    reg_val_now = await _get_value(page, "#region")
    if reg_val_now != "1":
        await _set_underlying_select(page, "#region", "1")
        await asyncio.sleep(0.2)
        await _sync_select2_container_text(page, "#region")

    log(f"[loc:summary] country=1 ok={ok_country}, region=1 ok={ok_region}, city={city_val} ok={ok_city}", "INFO")

# ---------- Main entry ----------

async def edit_macro_and_save(macro_id: str, values: dict):
    """
    Open macro edit page in a new tab, fill fields (including Location),
    submit form, and wait for server-side save/redirect/flash.
    """
    url = f"https://qima.taqeem.sa/report/macro/{macro_id}/edit"
    log(f"Editing macro #{macro_id} -> {url}", "STEP")
    page = await new_window(url)
    await asyncio.sleep(1.0)

    # Neutralize dialogs
    try:
        await page.evaluate("""() => {
          try { window.alert = () => {}; } catch(e){}
          try { window.confirm = () => true; } catch(e){}
          try { window.onbeforeunload = null; } catch(e){}
        }""")
    except Exception:
        pass

    async def set_in(id_, key, label):
        val = values.get(key, "")
        ok = await _set_input_value_by_id(page, id_, val)
        log(f"[fill] {label} ({id_}) <- {val} | ok={ok}", "INFO")

    async def set_sel(id_, key, label):
        val = values.get(key, "")
        ok = await _set_select_value_by_id(page, id_, val)
        log(f"[fill] {label} ({id_}) <- {val} | ok={ok}", "INFO")

    # Standard inputs/selects
    await set_in("asset_type", "asset_type", "asset_type")
    await set_in("asset_name", "asset_name", "asset_name")
    await set_sel("asset_usage_id", "asset_usage_id", "asset_usage_id")
    await set_in("inspected_at", "inspected_at", "inspected_at (date)")
    await set_in("value", "value", "value")
    await set_in("production_capacity", "production_capacity", "production_capacity")
    await set_in("production_capacity_measuring_unit", "production_capacity_measuring_unit", "production_capacity_measuring_unit")
    await set_in("owner_name", "owner_name", "owner_name")
    await set_in("product_type", "product_type", "product_type")

    await set_sel("approach1", "approach1_is_primary", "approach1_is_primary")
    await set_sel("approach3", "approach3_is_primary", "approach3_is_primary")
    await set_in("approach[3][value]", "approach3_value", "approach3_value")

    # Location (hard-coded values)
    await set_location_select2s(page, values)

    # Submit & wait
    mode = await _submit_via_save(page)
    ok_submit = mode != "no-btn"
    await asyncio.sleep(0.8)
    waited = await _wait_post_save(page, macro_id, timeout=12)
    log(f"[save] submit_mode={mode}, post-save-wait={waited}", "INFO")
    return ok_submit and waited
