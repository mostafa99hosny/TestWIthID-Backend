import asyncio
import sys
from scripts.core.browser.utils import wait_for_element, safe_query_selector_all, wait_for_table_rows
from pymongo import MongoClient
from datetime import datetime

# MongoDB connection setup
def get_mongo_client():
    """Initialize MongoDB client"""
    # Update these credentials with your actual MongoDB connection string
    MONGO_URI="mongodb+srv://test:JUL3OvyCSLVjSixj@assetval.pu3bqyr.mongodb.net/projectForever"
    return MongoClient(MONGO_URI)

def create_test_report_object(report_id, macro_ids_with_pages):
    """
    Create a TestReport object for MongoDB
    
    Args:
        report_id: The report ID
        macro_ids_with_pages: List of tuples (macro_id, page_number)
        
    Returns:
        Dictionary representing the TestReport document
    """
    return {
        'report_id': report_id,
        'title': f"Report {report_id}",
        'submitted_at': datetime.now().isoformat(),
        'checked': False,
        'asset_data': [
            {
                'id': str(macro_id),
                'serial_no': f"SN-{macro_id}",
                'asset_type': "0",
                'asset_name': f"Asset {macro_id}",
                'pg_no': str(page_num),  # Store the page number
                'model': "Default Model",
                'owner_name': "Unknown Owner",
                'submitState': 0,
                'year_made': "2024",
                'final_value': "0",
                'asset_usage_id': "0",
                'value_base': "0",
                'inspection_date': datetime.now().isoformat(),
                'production_capacity': "0",
                'production_capacity_measuring_unit': "0",
                'product_type': "0",
                'market_approach': "0",
                'market_approach_value': "0",
                'cost_approach': "0",
                'cost_approach_value': "0",
                'country': "المملكة العربية السعودية",
                'region': "Unknown Region",
                'city': "Unknown City"
            }
            for macro_id, page_num in macro_ids_with_pages
        ],
        'createdAt': datetime.now(),
        'updatedAt': datetime.now()
    }

async def save_to_mongodb(report_id, macro_ids_with_pages, db_name='projectForever', collection_name='testreports'):
    """
    Save the report data to MongoDB
    
    Args:
        report_id: The report ID
        macro_ids_with_pages: List of tuples (macro_id, page_number)
        db_name: MongoDB database name
        collection_name: MongoDB collection name
    """
    try:
        client = get_mongo_client()
        db = client[db_name]
        collection = db[collection_name]
        
        # Create the document
        test_report = create_test_report_object(report_id, macro_ids_with_pages)
        
        # Insert into MongoDB
        result = collection.insert_one(test_report)
        
        print(f"[MONGO_DB] Successfully saved report {report_id} with {len(macro_ids_with_pages)} assets to MongoDB. Document ID: {result.inserted_id}", file=sys.stderr)
        
        client.close()
        return True
        
    except Exception as e:
        print(f"[MONGO_DB] Error saving to MongoDB: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False

def get_balanced_page_distribution(total_pages, num_tabs):
    """
    Distribute pages evenly across tabs
    
    Args:
        total_pages: Total number of pages to process
        num_tabs: Number of browser tabs available
        
    Returns:
        List of lists, where each inner list contains page numbers for that tab
    """
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


async def get_macro_ids_from_page(page, base_url, page_num, tab_id):
    """
    Extract all macro IDs from a single page and its sub-pages
    
    Args:
        page: Browser page object
        base_url: Base URL of the report
        page_num: Page number to process
        tab_id: Tab identifier for logging
        
    Returns:
        List of tuples (macro_id, page_number) found on this page
    """
    local_macro_ids = []
    
    print(f"[MACRO_ID-TAB-{tab_id}] Processing page {page_num}", file=sys.stderr)
    
    try:
        # Navigate to the page
        page_url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
        await page.get(page_url)
        await asyncio.sleep(2)
        
        # Process all sub-pages (internal pagination)
        while True:
            await asyncio.sleep(2)
            table_ready = await wait_for_table_rows(page, timeout=100)
            if not table_ready:
                print(f"[MACRO_ID-TAB-{tab_id}] Table not found on page {page_num}, breaking", file=sys.stderr)
                break

            await asyncio.sleep(3)
            macro_cells = await safe_query_selector_all(page, "#m-table tbody tr td:nth-child(1) a")
            if not macro_cells:
                print(f"[MACRO_ID-TAB-{tab_id}] No macro cells found on page {page_num}, breaking", file=sys.stderr)
                break
            
            processed_count = 0
            
            for i, macro_cell in enumerate(macro_cells):
                try:
                    macro_id_text = macro_cell.text if macro_cell else None
                    
                    if not macro_id_text or not macro_id_text.strip():
                        continue
                        
                    macro_id = int(macro_id_text.strip())
                    # Store both macro_id and page number
                    local_macro_ids.append((macro_id, page_num))
                    processed_count += 1
                    
                except (ValueError, TypeError) as e:
                    print(f"[MACRO_ID-TAB-{tab_id}] WARNING Invalid macro ID on row {i}: {e}", file=sys.stderr)
                    continue
                except Exception as e:
                    print(f"[MACRO_ID-TAB-{tab_id}] ERROR processing row {i}: {e}", file=sys.stderr)
                    continue
            
            print(f"[MACRO_ID-TAB-{tab_id}] Page {page_num}: Found {processed_count} macro IDs", file=sys.stderr)
            
            # Check for next button (internal pagination)
            next_btn = await wait_for_element(page, "#m-table_next", timeout=5)
            if next_btn:
                attributes = next_btn.attrs
                classes = attributes.get("class_")
                if classes and "disabled" not in classes:
                    print(f"[MACRO_ID-TAB-{tab_id}] Clicking next sub-page button on page {page_num}", file=sys.stderr)
                    await next_btn.click()
                    await asyncio.sleep(3)
                    continue
            
            print(f"[MACRO_ID-TAB-{tab_id}] No more sub-pages on page {page_num}", file=sys.stderr)
            break
            
    except Exception as e:
        print(f"[MACRO_ID-TAB-{tab_id}] Error processing page {page_num}: {str(e)}", file=sys.stderr)
    
    return local_macro_ids


async def get_all_macro_ids_parallel(browser, report_id, tabs_num=3):
    """
    Main function to get all macro IDs and save to MongoDB
    
    Args:
        browser: Browser object
        report_id: Report ID to process
        tabs_num: Number of tabs to use for parallel processing
        
    Returns:
        List of macro IDs found
    """
    try:
        if not report_id:
            print("[MACRO_ID] No report_id provided", file=sys.stderr)
            return []
        
        base_url = f"https://qima.taqeem.sa/report/{report_id}"
        main_page = browser.tabs[0]
        await main_page.get(base_url)
        await asyncio.sleep(2)
        await wait_for_element(main_page, "li", timeout=30)

        # Get total number of pages from pagination
        pagination_links = await main_page.query_selector_all('ul.pagination li a')
        page_numbers = []

        for link in pagination_links:
            text = link.text
            if text and text.strip().isdigit():
                page_numbers.append(int(text.strip()))

        total_pages = max(page_numbers) if page_numbers else 1
        
        print(f"[MACRO_ID] Found {total_pages} pages to scan", file=sys.stderr)

        # Create pages for parallel processing
        pages = [main_page] + [
            await browser.get("about:blank", new_tab=True) 
            for _ in range(min(tabs_num - 1, total_pages - 1))
        ]

        # Distribute pages across tabs
        page_chunks = get_balanced_page_distribution(total_pages, len(pages))
        print(f"[MACRO_ID] Page distribution: {[len(chunk) for chunk in page_chunks]} pages per tab", file=sys.stderr)
        
        all_macro_ids_with_pages = []  # Now stores tuples (macro_id, page_number)
        macro_ids_lock = asyncio.Lock()

        async def process_pages_chunk(page, page_numbers_chunk, tab_id):
            """Process a chunk of pages in a single tab"""
            local_macro_ids_with_pages = []
            
            print(f"[MACRO_ID-TAB-{tab_id}] Processing pages: {page_numbers_chunk}", file=sys.stderr)
            
            for page_num in page_numbers_chunk:
                page_macro_ids = await get_macro_ids_from_page(page, base_url, page_num, tab_id)
                local_macro_ids_with_pages.extend(page_macro_ids)
            
            async with macro_ids_lock:
                all_macro_ids_with_pages.extend(local_macro_ids_with_pages)
                
            print(f"[MACRO_ID-TAB-{tab_id}] Completed processing, found {len(local_macro_ids_with_pages)} macro IDs", file=sys.stderr)

        # Process pages in parallel
        tasks = []
        for i, (page, chunk) in enumerate(zip(pages, page_chunks)):
            if chunk:
                tasks.append(process_pages_chunk(page, chunk, i))

        await asyncio.gather(*tasks)

        # Close extra tabs
        for p in pages[1:]:
            await p.close()

        print(f"[MACRO_ID] ID collection complete. Found {len(all_macro_ids_with_pages)} macro IDs", file=sys.stderr)
        
        # Save to MongoDB
        if all_macro_ids_with_pages:
            success = await save_to_mongodb(report_id, all_macro_ids_with_pages)
            if success:
                print(f"[MACRO_ID] Successfully saved all data to MongoDB", file=sys.stderr)
            else:
                print(f"[MACRO_ID] Failed to save data to MongoDB", file=sys.stderr)
        
        return {"status": "SUCCESS", "macro_ids_with_pages": all_macro_ids_with_pages}

    except Exception as e:
        print(f"[MACRO_ID] Error in get_all_macro_ids_parallel: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []