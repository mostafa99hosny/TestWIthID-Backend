import asyncio, time, json, sys

async def wait_for_element(page, selector, timeout=30, check_interval=0.5):
    """Wait for an element to appear on the page"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            element = await page.query_selector(selector)
            if element:
                return element
        except Exception:
            pass
        await asyncio.sleep(check_interval)
    return None

async def bulk_inject_inputs(page, macro_data, field_map, field_types):
    """Inject form data using JavaScript for better performance"""
    jsdata = {}

    for key, selector in field_map.items():
        if key not in macro_data:
            continue

        field_type = field_types.get(key, "text")
        value = str(macro_data[key] or "").strip()

        if field_type == "date" and value:
            try:
                from datetime import datetime
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

async def save_macros(page, macro_data, field_map, field_types, control_state=None):
    """Fill and save macro form"""
    from scripts.core.browser.worker_taqeem import check_control
    
    try:
        if control_state:
            await check_control(control_state)
        
        # Inject the macro data
        await bulk_inject_inputs(page, macro_data, field_map, field_types)
        
        if control_state:
            await check_control(control_state)
        
        # Click save button
        save_btn = await wait_for_element(page, "input[type='submit']", timeout=10)
        if save_btn:
            await asyncio.sleep(0.5)
            await save_btn.click()
            await asyncio.sleep(2)
            return {"status": "SAVED"}
        else:
            return {"status": "FAILED", "error": "Save button not found"}
            
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}

def calculate_tab_batches(total_macros, max_tabs, batch_size=10):
    """Calculate how to distribute macros across tabs"""
    if total_macros <= batch_size:
        return [total_macros]
    
    required_tabs = (total_macros + batch_size - 1) // batch_size
    tabs_to_use = min(required_tabs, max_tabs)

    base, extra = divmod(total_macros, tabs_to_use)
    result = []
    for i in range(tabs_to_use):
        size = base + (1 if i < extra else 0)
        result.append(size)
    return result

async def create_macros_multi_tab(browser, report_id, macro_count, macro_data_template, 
                                  field_map, field_types, max_tabs=3, batch_size=10, 
                                  control_state=None):
    from scripts.core.browser.worker_taqeem import check_control
    from datetime import datetime
    
    try:
        if control_state:
            await check_control(control_state)
        
        print(f"Starting macro creation: {macro_count} macros for report {report_id}")
        
        # Build asset creation URL
        asset_url = f"https://qima.taqeem.sa/report/asset/create/{report_id}"
        
        # Navigate main page
        main_page = await browser.get(asset_url)
        await asyncio.sleep(2)
        
        if control_state:
            await check_control(control_state)
        
        # Verify we're on the correct page
        current_url = await main_page.evaluate("window.location.href")
        if str(report_id) not in current_url:
            return {
                "status": "FAILED",
                "error": f"Failed to navigate to asset creation page for report {report_id}"
            }
        
        print(f"Successfully navigated to: {current_url}")
        
        # Calculate tab distribution
        distribution = calculate_tab_batches(macro_count, max_tabs, batch_size)
        print(f"Tab distribution: {distribution} macros per tab")
        
        # Create additional tabs
        pages = [main_page]
        for _ in range(len(distribution) - 1):
            if control_state:
                await check_control(control_state)
            new_tab = await browser.get(asset_url, new_tab=True)
            pages.append(new_tab)
            await asyncio.sleep(1)
        
        # Wait for all pages to be ready
        for page in pages:
            for _ in range(20):
                if control_state:
                    await check_control(control_state)
                ready_state = await page.evaluate("document.readyState")
                key_el = await wait_for_element(page, "#macros", timeout=0.5)
                if ready_state == "complete" and key_el:
                    break
                await asyncio.sleep(0.5)
        
        completed = 0
        total_created = 0
        
        async def process_macros_in_tab(page, start_index, count):
            """Process a set of macros in a single tab"""
            nonlocal completed, total_created
            
            for batch_start in range(0, count, batch_size):
                if control_state:
                    await check_control(control_state)
                
                batch_count = min(batch_size, count - batch_start)
                
                print(f"Processing batch: {start_index + batch_start} to {start_index + batch_start + batch_count - 1}")
                
                # Prepare macro data for this batch
                batch_data = {
                    "number_of_macros": str(batch_count),
                    "asset_data": []
                }
                
                # If macro_data_template is a list, use it; otherwise replicate the template
                if isinstance(macro_data_template, list):
                    # Use provided macro data
                    for i in range(batch_count):
                        idx = start_index + batch_start + i
                        if idx < len(macro_data_template):
                            batch_data["asset_data"].append(macro_data_template[idx])
                        else:
                            # If we run out of template data, use the last one
                            batch_data["asset_data"].append(macro_data_template[-1])
                else:
                    # Use template for all macros
                    batch_data["asset_data"] = [macro_data_template] * batch_count
                
                # Merge macro data with batch data for form filling
                form_data = {**batch_data, **macro_data_template} if isinstance(macro_data_template, dict) else batch_data
                
                # Save the macros
                result = await save_macros(page, form_data, field_map, field_types, control_state)
                
                if result.get("status") == "FAILED":
                    print(f"Failed to save batch: {result.get('error')}")
                    return result
                
                completed += batch_count
                total_created += batch_count
                
                print(f"Progress: {completed}/{macro_count} macros created ({round((completed/macro_count)*100, 2)}%)")
                
                # If there are more batches, reload the page
                if batch_start + batch_size < count:
                    if control_state:
                        await check_control(control_state)
                    await page.get(asset_url)
                    await asyncio.sleep(1)
            
            return {"status": "SUCCESS"}
        
        # Create tasks for parallel processing
        tasks = []
        idx = 0
        for page, count in zip(pages, distribution):
            tasks.append(process_macros_in_tab(page, idx, count))
            idx += count
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks)
        
        # Check for failures
        for result in results:
            if isinstance(result, dict) and result.get("status") == "FAILED":
                return result
        
        # Close extra tabs
        for p in pages[1:]:
            await p.close()
        
        print(f"Successfully created {total_created} macros for report {report_id}")
        
        return {
            "status": "SUCCESS",
            "report_id": report_id,
            "total_created": total_created,
            "completion_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error in create_macros_multi_tab: {str(e)}")
        return {
            "status": "FAILED",
            "error": str(e)
        }