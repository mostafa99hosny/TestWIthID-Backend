import asyncio, json, time, sys
from datetime import datetime

async def wait_for_table_rows(page, timeout=100):
    """Wait for table to have valid data rows"""
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            # Method 1: Check if we can directly find valid macro cells
            macro_cells = await page.query_selector_all("#m-table tbody tr td:nth-child(1) a")
            
            for cell in macro_cells:
                cell_text = cell.text
                if cell_text and cell_text.strip().isdigit():
                    return True  # Found at least one valid macro ID
                    
            # Method 2: If no valid cells found, wait and retry
            await asyncio.sleep(0.5)
            
        except Exception as e:
            # If anything fails, just wait and retry
            await asyncio.sleep(0.5)
            continue
    
    return False

def emit_progress(status, message, batch_id, asset_index=None, tab_id=None, **kwargs):
    progress_data = {
        "type": "PROGRESS",
        "status": status,
        "message": message,
        "batchId": batch_id,
        "assetIndex": asset_index,
        "tabId": tab_id,
        "timestamp": time.time(),
        **kwargs
    }
    print(json.dumps(progress_data), flush=True)


async def safe_query_selector_all(page, selector):
    """Safely query multiple elements without stale element issues"""
    try:
        return await page.query_selector_all(selector)
    except Exception as e:
        print(f"Error querying {selector}: {e}", file=sys.stderr)
        return []
    
async def wait_for_element(page, selector, timeout=30):
    """Wait for element with timeout"""
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            element = await page.query_selector(selector)
            if element:
                return element
            await asyncio.sleep(0.5)
        except Exception as e:
            await asyncio.sleep(0.5)
            continue
    
    return None
    
def log(msg: str, level: str = "INFO"):
    stamp = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO":"ℹ️", "OK":"✅", "ERR":"❌", "STEP":"👉"}
    print(f"{icons.get(level,'ℹ️')} [{stamp}] {msg}", flush=True)


async def wait_for_table_rows(page, timeout=100):
    """Wait for table to have valid data rows"""
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            # Method 1: Check if we can directly find valid macro cells
            macro_cells = await page.query_selector_all("#m-table tbody tr td:nth-child(1) a")
            
            for cell in macro_cells:
                cell_text = cell.text
                if cell_text and cell_text.strip().isdigit():
                    return True  # Found at least one valid macro ID
                    
            # Method 2: If no valid cells found, wait and retry
            await asyncio.sleep(0.5)
            
        except Exception as e:
            # If anything fails, just wait and retry
            await asyncio.sleep(0.5)
            continue
    
    return False