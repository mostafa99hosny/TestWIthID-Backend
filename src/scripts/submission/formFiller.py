import asyncio, json, sys
from scripts.core.browser.worker_taqeem import check_control
from scripts.core.browser.utils import wait_for_element
from datetime import datetime

_location_cache = {}
async def set_location(page, country_name, region_name, city_name):
    try:
        import re, unicodedata

        cache_key = f"{country_name}|{region_name}|{city_name}"

        def normalize_text(text: str) -> str:
            if not text:
                return ""
            text = unicodedata.normalize("NFKC", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()

        async def wait_for_options(selector, min_options=2, timeout=10):
            for _ in range(timeout * 2):
                el = await wait_for_element(page, selector, timeout=1)
                if el and getattr(el, "children", None) and len(el.children) >= min_options:
                    return el
                await asyncio.sleep(0.5)
            return None

        async def get_location_code(name, selector):
            if not name:
                return None
            el = await wait_for_options(selector)
            if not el:
                return None
            for opt in el.children:
                text = normalize_text(opt.text)
                if normalize_text(name).lower() in text.lower():
                    return opt.attrs.get("value")
            return None

        async def set_field(selector, value):
            if not value:
                return
            args = json.dumps({"selector": selector, "value": value})
            await page.evaluate(f"""
                (function() {{
                    const args = {args};
                    if (window.$) {{
                        window.$(args.selector).val(args.value).trigger("change");
                    }} else {{
                        const el = document.querySelector(args.selector);
                        if (!el) return;
                        if (el.value !== args.value) {{
                            el.value = args.value;
                            el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                            el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                        }}
                    }}
                }})();
            """)

        region_code, city_code = _location_cache.get(cache_key, (None, None))

        if not region_code:
            region_code = await get_location_code(region_name, "#region")
        if not city_code:
            city_code = await get_location_code(city_name, "#city")

        if region_code or city_code:
            _location_cache[cache_key] = (region_code, city_code)

        await set_field("#country_id", "1")
        await asyncio.sleep(0.5)
        await set_field("#region", region_code)
        await asyncio.sleep(0.5)
        await set_field("#city", city_code)
        await asyncio.sleep(0.5)

        return True

    except Exception as e:
        print(f"Location injection failed: {e}", file=sys.stderr)
        return False 

async def bulk_inject_inputs(page, record, field_map, field_types):
    jsdata = {}

    for key, selector in field_map.items():
        if key not in record:
            continue

        field_type = field_types.get(key, "text")
        value = str(record[key] or "").strip()

        if field_type == "date" and value:
            try:
                value = datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")
            except ValueError:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    print(f"[WARNING] Invalid date format for {key}: {value}", file=sys.stderr)
                    continue

        jsdata[selector] = {"type": field_type, "value": value}

    js = f"""
    (function() {{
        const data = {json.dumps(jsdata)};
        for (const [selector, meta] of Object.entries(data)) {{
            const el = document.querySelector(selector);
            if (!el) continue;

            switch(meta.type) {{
                case "checkbox":
                    el.checked = Boolean(meta.value);
                    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    break;

                case "select":
                    let found = false;
                    for (const opt of el.options) {{
                        if (opt.value == meta.value || opt.text == meta.value) {{
                            el.value = opt.value;
                            found = true;
                            break;
                        }}
                    }}
                    if (!found && el.options.length) {{
                        el.selectedIndex = 0;
                    }}
                    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    break;

                case "radio":
                    const labels = document.querySelectorAll('label.form-check-label');
                    for (const lbl of labels) {{
                        if ((lbl.innerText || '').trim() === meta.value) {{
                            const radio = document.getElementById(lbl.getAttribute('for'));
                            if (radio) {{
                                radio.checked = true;
                                radio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                            break;
                        }}
                    }}
                    break;

                case "date":
                case "text":
                default:
                    el.value = meta.value ?? "";
                    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    break;
            }}
        }}
    }})();
    """

    await page.evaluate(js)

async def fill_form(page, record, field_map, field_types, is_last_step=False, retries=0, max_retries=2, skip_special_fields=False, control_state=None, report_id=None):
    try:
        if control_state:
            await check_control(control_state)
        
        await bulk_inject_inputs(page, record, field_map, field_types)

        for key, selector in field_map.items():
            if key not in record: continue
            value = str(record[key] or "")
            ftype = field_types.get(key,"text")
            try:
                if ftype == "location":
                    country_name = record.get("country","")
                    region_name = record.get("region","")
                    city_name = record.get("city","")
                    await set_location(page, country_name, region_name, city_name)

                elif ftype == "file":
                    file_input = await wait_for_element(page, selector, timeout=10)
                    if file_input: await file_input.send_file(value)
                    
                elif ftype == "dynamic_select":
                    select_element = await wait_for_element(page, selector, timeout=10)
                    if select_element:
                        for opt in select_element.children:
                            if value.lower() in (opt.text or "").lower():
                                await opt.select_option()
                                break

            except Exception:
                continue
    
        if not is_last_step:
            continue_btn = await wait_for_element(page, "input[name='continue']", timeout=10)
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(2)
                error_div = await wait_for_element(page, "div.alert.alert-danger", timeout=5)
                if error_div and retries < max_retries:
                    await asyncio.sleep(1)
                    return await fill_form(page, record, field_map, field_types, is_last_step, retries+1, max_retries, skip_special_fields, control_state, report_id)
        else:
            save_btn = await wait_for_element(page, "input[type='submit']", timeout=10)
            if save_btn:
                await asyncio.sleep(0.5)
                await save_btn.click()
                await asyncio.sleep(2)
                return {"status":"SAVED"}
            else:
                return {"status":"FAILED","error":"Save button not found"}
        return True
    except Exception as e:
        return {"status":"FAILED","error": str(e)}