import asyncio, traceback
from motor.motor_asyncio import AsyncIOMotorClient
from scripts.core.browser.utils import wait_for_element, safe_query_selector_all, wait_for_table_rows

MONGO_URI = "mongodb+srv://test:JUL3OvyCSLVjSixj@assetval.pu3bqyr.mongodb.net/projectForever"
client = AsyncIOMotorClient(MONGO_URI)
db = client["projectForever"]

async def check_incomplete_macros(browser, report_id, browsers_num=3):
    try:
        # First, fetch report to map macro IDs
        report = await db.testreports.find_one({"report_id": report_id})
        if not report:
            return {"status": "FAILED", "error": f"Report {report_id} not found in testreports"}

        # For half check, get only incomplete macro IDs from database
        incomplete_macro_ids = set()
            

        base_url = f"https://qima.taqeem.sa/report/{report_id}"
        main_page = await browser.get(base_url)
        await asyncio.sleep(1)

        # Check for delete button first
        delete_btn = await wait_for_element(main_page, "#delete_report", timeout=5)
        if delete_btn:
            print("[INFO] Delete button exists, assuming all macros complete.")
            # Mark all assets as complete
            await db.testreports.update_one(
                {"report_id": report_id},
                {"$set": {f"asset_data.{i}.submitState": 1 for i in range(len(report.get("asset_data", [])))}}
            )
            return {"status": "SUCCESS", "incomplete_ids": [], "macro_count": 0, "message": "All macros complete"}

        # Get total number of pages from pagination
        pagination_links = await main_page.query_selector_all('ul.pagination li a')
        page_numbers = []

        for link in pagination_links:
            text = link.text
            if text and text.strip().isdigit():
                page_numbers.append(int(text.strip()))

        total_pages = max(page_numbers) if page_numbers else 1
        print(f"[CHECK] Found {total_pages} pages to process with {browsers_num} tabs")

        # Create pages for parallel processing
        pages = [main_page] + [await browser.get("about:blank", new_tab=True) for _ in range(min(browsers_num - 1, total_pages - 1))]

        # Balanced page distribution
        def get_balanced_page_distribution(total_pages, num_tabs):
            if total_pages <= 0 or num_tabs <= 0:
                return [[] for _ in range(num_tabs)]
            
            base_pages_per_tab = total_pages // num_tabs
            remainder = total_pages % num_tabs
            
            distribution = []
            current_page = 1
            
            for tab_index in range(num_tabs):
                pages_this_tab = base_pages_per_tab + (1 if tab_index < remainder else 0)
                
                if pages_this_tab > 0:
                    tab_pages = list(range(current_page, current_page + pages_this_tab))
                    distribution.append(tab_pages)
                    current_page += pages_this_tab
                else:
                    distribution.append([])
            
            return distribution

        page_chunks = get_balanced_page_distribution(total_pages, len(pages))

        print(f"[CHECK] Page distribution: {[len(chunk) for chunk in page_chunks]} pages per tab")
        
        incomplete_ids = []
        incomplete_ids_lock = asyncio.Lock()
        
        # Track all processed macros to handle missing ones
        all_processed_macros = set()
        processed_macros_lock = asyncio.Lock()

        async def process_pages_chunk(page, page_numbers_chunk, tab_id):
            local_incomplete = []
            local_processed = set()
            
            print(f"[TAB-{tab_id}] Processing pages: {page_numbers_chunk}")
            
            for page_num in page_numbers_chunk:
                print(f"[TAB-{tab_id}] Processing page {page_num}")
                
                try:
                    # Navigate to the specific page
                    page_url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
                    await page.get(page_url)
                    await asyncio.sleep(2)
                    
                    # Inner loop for table sub-pages (internal pagination)
                    while True:
                        # Wait for table to load
                        table_ready = await wait_for_table_rows(page, timeout=100)
                        if not table_ready:
                            print(f"[TAB-{tab_id}] Timeout waiting for table rows on page {page_num}")
                            break
                        
                        await asyncio.sleep(3)
                        macro_cells = await safe_query_selector_all(page, "#m-table tbody tr td:nth-child(1) a")
                        status_cells = await safe_query_selector_all(page, "#m-table tbody tr td:nth-child(6)")
                        
                        start_index = 0
                        
                        processed_count = 0
                        incomplete_count = 0
                        
                        for i in range(start_index, len(macro_cells)):
                            try:
                                if i >= len(status_cells):
                                    break
                                    
                                macro_cell = macro_cells[i]
                                status_cell = status_cells[i]
                                
                                macro_id_text = macro_cell.text if macro_cell else None
                                status_text = status_cell.text if status_cell else ""
                                
                                if not macro_id_text or not macro_id_text.strip():
                                    continue
                                    
                                macro_id = int(macro_id_text.strip())
                                local_processed.add(macro_id)  
                                
                                submit_state = 0 if "غير مكتملة" in status_text else 1

                                # Update database - FIXED: More robust update logic
                                update_result = await db.testreports.update_one(
                                    {"report_id": report_id, "asset_data.id": str(macro_id)},
                                    {"$set": {"asset_data.$.submitState": submit_state}}
                                )

                                # If no document was matched, try to update using array index
                                if update_result.matched_count == 0:
                                    # Find the index of the asset with this macro_id
                                    report_after = await db.testreports.find_one({"report_id": report_id})
                                    if report_after:
                                        asset_data = report_after.get("asset_data", [])
                                        for idx, asset in enumerate(asset_data):
                                            if asset.get("id") == macro_id:
                                                await db.testreports.update_one(
                                                    {"report_id": report_id},
                                                    {"$set": {f"asset_data.{idx}.submitState": submit_state}}
                                                )
                                                print(f"[TAB-{tab_id}] Updated Macro {macro_id} using index {idx}")
                                                break

                                print(f"[TAB-{tab_id}] Processed Macro {macro_id} on page {page_num}, submitState={submit_state}, matched={update_result.matched_count}, modified={update_result.modified_count}")

                                processed_count += 1
                                
                                if submit_state == 0:
                                    print(f"[TAB-{tab_id}] INCOMPLETE Macro {macro_id} on page {page_num}")
                                    local_incomplete.append(macro_id)
                                    incomplete_count += 1
                                    
                            except (ValueError, TypeError) as e:
                                print(f"[TAB-{tab_id}] WARNING Invalid macro ID on row {i}: {e}")
                                continue
                            except Exception as e:
                                print(f"[TAB-{tab_id}] ERROR processing row {i}: {e}")
                                continue
                        
                        print(f"[TAB-{tab_id}] Page {page_num}: Processed {processed_count} macros, {incomplete_count} incomplete")
                    
                        # Check for next button
                        next_btn = await wait_for_element(page, "#m-table_next", timeout=5)
                        if next_btn:
                            attributes = next_btn.attrs
                            classes = attributes.get("class_")
                            if "disabled" not in classes:
                                print(f"[TAB-{tab_id}] Clicking next sub-page button on page {page_num}")
                                await next_btn.click()
                                await asyncio.sleep(2)
                                continue
                        
                        # No more sub-pages, break inner loop
                        print(f"[TAB-{tab_id}] No more sub-pages on page {page_num}")
                        break
                        
                except Exception as e:
                    print(f"[TAB-{tab_id}] ERROR processing page {page_num}: {str(e)}")
                    continue
            
            async with incomplete_ids_lock:
                incomplete_ids.extend(local_incomplete)
                
            async with processed_macros_lock:
                all_processed_macros.update(local_processed)
                
            print(f"[TAB-{tab_id}] Completed processing, found {len(local_incomplete)} incomplete macros, processed {len(local_processed)} total macros")

        # Process pages in parallel
        tasks = []
        for i, (page, chunk) in enumerate(zip(pages, page_chunks)):
            if chunk:  # Only create tasks for tabs that have pages to process
                tasks.append(process_pages_chunk(page, chunk, i))

        # Process pages in parallel
        await asyncio.gather(*tasks)

        # Close extra tabs
        for p in pages[1:]:
            await p.close()

        return {
            "status": "SUCCESS",
            "incomplete_ids": incomplete_ids,
            "macro_count": len(incomplete_ids),
            "total_pages_processed": total_pages,
            "tabs_used": len(pages),
            "total_macros_processed": len(all_processed_macros)
        }

    except Exception as e:
        tb = traceback.format_exc()
        print("[CHECK] Error:", tb)
        return {"status": "FAILED", "error": str(e), "traceback": tb}

async def half_check_incomplete_macros(browser, report_id, browsers_num=3):
    try:
        print(f"[HALF CHECK] Starting optimized half check for report {report_id}")

        # First, fetch report to get incomplete macros and their page numbers
        report = await db.testreports.find_one({"report_id": report_id})
        if not report:
            return {"status": "FAILED", "error": f"Report {report_id} not found in testreports"}

        # Check for delete button first (same logic as full check)
        base_url = f"https://qima.taqeem.sa/report/{report_id}"
        main_page = await browser.get(base_url)
        await asyncio.sleep(1)

        delete_btn = await wait_for_element(main_page, "#delete_report", timeout=5)
        if delete_btn:
            print("[HALF CHECK] Delete button exists, assuming all macros complete.")
            # Mark all assets as complete
            await db.testreports.update_one(
                {"report_id": report_id},
                {"$set": {f"asset_data.{i}.submitState": 1 for i in range(len(report.get("asset_data", [])))}}
            )
            return {"status": "SUCCESS", "incomplete_ids": [], "macro_count": 0, "message": "All macros complete"}

        # Collect incomplete macro IDs and their page numbers
        # FIX: Convert to integers for consistent comparison
        incomplete_macro_ids = set()
        incomplete_page_numbers = set()
        
        asset_data = report.get("asset_data", [])
        for asset in asset_data:
            if asset.get("submitState") == 0:
                macro_id = asset.get("id")
                # Convert to int for consistent comparison
                try:
                    incomplete_macro_ids.add(int(macro_id))
                except (ValueError, TypeError):
                    print(f"[HALF CHECK] WARNING: Invalid macro_id in DB: {macro_id}")
                    continue
                
                # Get page number from pg_no field
                pg_no = asset.get("pg_no")
                if pg_no is not None:
                    incomplete_page_numbers.add(int(pg_no))
        
        print(f"[HALF CHECK] Found {len(incomplete_macro_ids)} incomplete macros in DB: {sorted(list(incomplete_macro_ids))[:10]}...")
        print(f"[HALF CHECK] Found {len(incomplete_page_numbers)} unique pages with incomplete macros: {sorted(incomplete_page_numbers)}")
        
        # If no incomplete macros in DB, return early with same format as full check
        if not incomplete_macro_ids:
            return {
                "status": "SUCCESS", 
                "incomplete_ids": [],
                "macro_count": 0,
                "total_pages_processed": 0,
                "tabs_used": 1,
                "total_macros_processed": 0,
                "message": "No incomplete macros found in database"
            }

        # Get total number of pages from pagination (same as full check)
        pagination_links = await main_page.query_selector_all('ul.pagination li a')
        page_numbers = []

        for link in pagination_links:
            text = link.text
            if text and text.strip().isdigit():
                page_numbers.append(int(text.strip()))

        total_pages = max(page_numbers) if page_numbers else 1
        print(f"[HALF CHECK] Total pages available: {total_pages}, will process {len(incomplete_page_numbers)} pages with incomplete macros")

        # Only process pages that contain incomplete macros, but ensure they exist in pagination
        target_pages = [p for p in sorted(incomplete_page_numbers) if p <= total_pages]
        
        # If no valid target pages, return
        if not target_pages:
            print(f"[HALF CHECK] No valid target pages found within total pages {total_pages}")
            return {
                "status": "SUCCESS",
                "incomplete_ids": [],
                "macro_count": 0,
                "total_pages_processed": 0,
                "tabs_used": 1,
                "total_macros_processed": 0,
                "message": "No valid pages with incomplete macros found"
            }

        print(f"[HALF CHECK] Will process {len(target_pages)} pages: {target_pages} with {browsers_num} tabs")

        # Create pages for parallel processing (same logic as full check)
        pages_needed = min(browsers_num, len(target_pages))
        pages = [main_page] + [await browser.get("about:blank", new_tab=True) for _ in range(pages_needed - 1)]

        # Use the same balanced distribution function as full check
        def get_balanced_page_distribution(total_pages, num_tabs):
            if total_pages <= 0 or num_tabs <= 0:
                return [[] for _ in range(num_tabs)]
            
            base_pages_per_tab = total_pages // num_tabs
            remainder = total_pages % num_tabs
            
            distribution = []
            current_page = 1
            
            for tab_index in range(num_tabs):
                pages_this_tab = base_pages_per_tab + (1 if tab_index < remainder else 0)
                
                if pages_this_tab > 0:
                    tab_pages = list(range(current_page, current_page + pages_this_tab))
                    distribution.append(tab_pages)
                    current_page += pages_this_tab
                else:
                    distribution.append([])
            
            return distribution

        # Distribute target pages among tabs using the same balanced algorithm
        page_chunks = get_balanced_page_distribution(len(target_pages), len(pages))
        
        # Map the distribution indices back to actual page numbers
        actual_page_chunks = []
        current_index = 0
        for chunk in page_chunks:
            chunk_size = len(chunk)
            if chunk_size > 0:
                actual_chunk = target_pages[current_index:current_index + chunk_size]
                actual_page_chunks.append(actual_chunk)
                current_index += chunk_size
            else:
                actual_page_chunks.append([])

        print(f"[HALF CHECK] Page distribution: {[len(chunk) for chunk in actual_page_chunks]} pages per tab")
        
        incomplete_ids = []
        incomplete_ids_lock = asyncio.Lock()
        
        # Track all processed macros
        all_processed_macros = set()
        processed_macros_lock = asyncio.Lock()

        async def process_pages_chunk(page, page_numbers_chunk, tab_id):
            local_incomplete = []
            local_processed = set()
            local_skipped = 0
            
            print(f"[HALF-TAB-{tab_id}] Processing pages: {page_numbers_chunk}")
            
            for page_num in page_numbers_chunk:
                print(f"[HALF-TAB-{tab_id}] Processing page {page_num}")
                
                try:
                    # Navigate to the specific page
                    page_url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
                    await page.get(page_url)
                    await asyncio.sleep(2)
                    
                    # Inner loop for table sub-pages (internal pagination) - same as full check
                    while True:
                        # Wait for table to load
                        table_ready = await wait_for_table_rows(page, timeout=100)
                        if not table_ready:
                            print(f"[HALF-TAB-{tab_id}] Timeout waiting for table rows on page {page_num}")
                            break
                        
                        await asyncio.sleep(3)
                        macro_cells = await safe_query_selector_all(page, "#m-table tbody tr td:nth-child(1) a")
                        status_cells = await safe_query_selector_all(page, "#m-table tbody tr td:nth-child(6)")
                        
                        processed_count = 0
                        incomplete_count = 0
                        
                        for i in range(len(macro_cells)):
                            try:
                                if i >= len(status_cells):
                                    break
                                    
                                macro_cell = macro_cells[i]
                                status_cell = status_cells[i]
                                
                                macro_id_text = macro_cell.text if macro_cell else None
                                status_text = status_cell.text if status_cell else ""
                                
                                if not macro_id_text or not macro_id_text.strip():
                                    continue
                                    
                                macro_id = int(macro_id_text.strip())
                                
                                # Only process macros that are marked as incomplete in DB
                                if macro_id not in incomplete_macro_ids:
                                    local_skipped += 1
                                    continue
                                
                                local_processed.add(macro_id)
                                submit_state = 0 if "غير مكتملة" in status_text else 1

                                # Update database - same logic as full check
                                update_result = await db.testreports.update_one(
                                    {"report_id": report_id, "asset_data.id": str(macro_id)},
                                    {"$set": {"asset_data.$.submitState": submit_state}}
                                )

                                # If no document was matched, try to update using array index
                                if update_result.matched_count == 0:
                                    report_after = await db.testreports.find_one({"report_id": report_id})
                                    if report_after:
                                        asset_data = report_after.get("asset_data", [])
                                        for idx, asset in enumerate(asset_data):
                                            if asset.get("id") == str(macro_id):  # DB stores as string
                                                await db.testreports.update_one(
                                                    {"report_id": report_id},
                                                    {"$set": {f"asset_data.{idx}.submitState": submit_state}}
                                                )
                                                print(f"[HALF-TAB-{tab_id}] Updated Macro {macro_id} using index {idx}")
                                                break

                                print(f"[HALF-TAB-{tab_id}] Processed Macro {macro_id} on page {page_num}, submitState={submit_state}, matched={update_result.matched_count}")

                                processed_count += 1
                                
                                if submit_state == 0:
                                    print(f"[HALF-TAB-{tab_id}] STILL INCOMPLETE Macro {macro_id} on page {page_num}")
                                    local_incomplete.append(macro_id)
                                    incomplete_count += 1
                                else:
                                    print(f"[HALF-TAB-{tab_id}] NOW COMPLETE Macro {macro_id} on page {page_num}")
                                    
                            except (ValueError, TypeError) as e:
                                print(f"[HALF-TAB-{tab_id}] WARNING Invalid macro ID on row {i}: {e}")
                                continue
                            except Exception as e:
                                print(f"[HALF-TAB-{tab_id}] ERROR processing row {i}: {e}")
                                continue
                        
                        print(f"[HALF-TAB-{tab_id}] Page {page_num}: Processed {processed_count} target macros, {incomplete_count} still incomplete, skipped {local_skipped} non-target macros")
                    
                        # Check for next button - same as full check
                        next_btn = await wait_for_element(page, "#m-table_next", timeout=5)
                        if next_btn:
                            attributes = next_btn.attrs
                            classes = attributes.get("class_")
                            if "disabled" not in classes:
                                print(f"[HALF-TAB-{tab_id}] Clicking next sub-page button on page {page_num}")
                                await next_btn.click()
                                await asyncio.sleep(2)
                                continue
                        
                        # No more sub-pages, break inner loop
                        print(f"[HALF-TAB-{tab_id}] No more sub-pages on page {page_num}")
                        break
                        
                except Exception as e:
                    print(f"[HALF-TAB-{tab_id}] ERROR processing page {page_num}: {str(e)}")
                    continue
            
            async with incomplete_ids_lock:
                incomplete_ids.extend(local_incomplete)
                
            async with processed_macros_lock:
                all_processed_macros.update(local_processed)
                
            print(f"[HALF-TAB-{tab_id}] Completed processing, found {len(local_incomplete)} still incomplete, processed {len(local_processed)} target macros, skipped {local_skipped} non-target macros")

        # Process pages in parallel - same as full check
        tasks = []
        for i, (page, chunk) in enumerate(zip(pages, actual_page_chunks)):
            if chunk:  # Only create tasks for tabs that have pages to process
                tasks.append(process_pages_chunk(page, chunk, i))

        # Process pages in parallel
        await asyncio.gather(*tasks)

        # Close extra tabs - same as full check
        for p in pages[1:]:
            await p.close()

        # Check if we found all incomplete macros
        missing_macros = incomplete_macro_ids - all_processed_macros
        if missing_macros:
            print(f"[HALF CHECK] WARNING: {len(missing_macros)} incomplete macros not found on their expected pages: {sorted(list(missing_macros))}")
            # Mark missing macros as complete since we couldn't find them
            for macro_id in missing_macros:
                await db.testreports.update_one(
                    {"report_id": report_id, "asset_data.id": str(macro_id)},
                    {"$set": {"asset_data.$.submitState": 1}}
                )
                print(f"[HALF CHECK] Marked missing macro {macro_id} as complete")

        # Return same format as full check
        return {
            "status": "SUCCESS",
            "incomplete_ids": incomplete_ids,
            "macro_count": len(incomplete_ids),
            "total_pages_processed": len(target_pages),
            "tabs_used": len(pages),
            "total_macros_processed": len(all_processed_macros),
            "missing_macros_found": len(missing_macros) if missing_macros else 0
        }

    except Exception as e:
        tb = traceback.format_exc()
        print("[HALF CHECK] Error:", tb)
        return {"status": "FAILED", "error": str(e), "traceback": tb}

async def RunCheckMacroStatus(browser, report_id, tabs_num=3):
    """Full check - processes all pages"""
    result = await check_incomplete_macros(browser, report_id, tabs_num)
    return result

async def RunHalfCheckMacroStatus(browser, report_id, tabs_num=3):
    """Optimized half check - only processes pages with incomplete macros"""
    result = await half_check_incomplete_macros(browser, report_id, tabs_num)
    return result