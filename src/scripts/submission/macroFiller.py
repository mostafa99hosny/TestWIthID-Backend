import asyncio, traceback, sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from .formSteps import macro_form_config
from .formFiller import fill_form
from scripts.core.browser.utils import wait_for_element, emit_progress
from scripts.core.browser.worker_taqeem import check_control

MONGO_URI = "mongodb+srv://test:JUL3OvyCSLVjSixj@assetval.pu3bqyr.mongodb.net/projectForever"
client = AsyncIOMotorClient(MONGO_URI)
db = client["projectForever"]

def balanced_chunks(lst, n):
    """Split list into n balanced chunks"""
    k, m = divmod(len(lst), n)
    chunks = []
    start = 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        chunks.append(lst[start:start+size])
        start += size
    return chunks

async def fill_macro_form(page, macro_id, macro_data, field_map, field_types, control_state=None, report_id=None):
    """Fill and submit a single macro edit form"""
    await page.get(f"https://qima.taqeem.sa/report/macro/{macro_id}/edit")
    
    await wait_for_element(page, "#value_base_id", timeout=30)

    try:
        result = await fill_form(
            page, 
            macro_data, 
            field_map, 
            field_types, 
            is_last_step=True, 
            skip_special_fields=True, 
            control_state=control_state, 
            report_id=report_id
        )
        return result
    except Exception as e:
        print(f"Filling macro {macro_id} failed: {e}", file=sys.stderr)
        return {"status": "FAILED", "error": str(e)}

async def handle_macro_edits(browser, record, tabs_num=3, control_state=None, record_id=None):
    """
    Edit macros in parallel using multiple tabs
    Expects asset_data to already have 'id' field populated for each asset
    """    
    asset_data = record.get("asset_data", [])
    if not asset_data: 
        return {"status": "SUCCESS", "message": "No assets to edit"}

    if control_state:
        await check_control(control_state)

    total_assets = len(asset_data)
    
    # Verify all assets have IDs
    missing_ids = [i for i, asset in enumerate(asset_data) if not asset.get("id")]
    if missing_ids:
        error_msg = f"Missing macro IDs for assets at indices: {missing_ids}"
        # Emit with type field for socket routing
        emit_progress(
            "FAILED",
            error_msg,
            record_id,
            error=error_msg,
            progress_type="MACRO_EDIT"
        )
        return {"status": "FAILED", "error": error_msg}

    # Emit start progress
    emit_progress(
        "STARTING",
        f"Starting to edit {total_assets} macros using {tabs_num} tabs",
        record_id,
        total=total_assets,
        current=0,
        percentage=0.0,
        numTabs=tabs_num,
        progress_type="MACRO_EDIT"
    )
    
    print(f"Asset data with IDs: {[(i, asset.get('id')) for i, asset in enumerate(asset_data)]}")

    # Create pages for parallel processing
    main_page = browser.tabs[0]
    pages = [main_page] + [await browser.get("", new_tab=True) for _ in range(tabs_num - 1)]

    # Split assets into balanced chunks
    asset_chunks = balanced_chunks(asset_data, tabs_num)

    completed = 0
    failed = 0
    completed_lock = asyncio.Lock()

    async def process_chunk(asset_chunk, page, chunk_index):
        nonlocal completed, failed
        print(f"Processing chunk {chunk_index} with {len(asset_chunk)} assets")
        
        for asset_index, asset in enumerate(asset_chunk):
            if control_state:
                await check_control(control_state)
            
            macro_id = asset.get("id")
            
            if macro_id is None:
                print(f"ERROR: macro_id is None for asset index {asset_index} in chunk {chunk_index}")
                async with completed_lock:
                    failed += 1
                continue
            
            try:
                print(f"Editing macro {macro_id} (chunk {chunk_index}, asset {asset_index})")
                if control_state:
                    await check_control(control_state)
                
                result = await fill_macro_form(
                    page,
                    macro_id,
                    asset,
                    macro_form_config["field_map"],
                    macro_form_config["field_types"],
                    control_state,
                    record_id
                )
                
                async with completed_lock:
                    if result.get("status") == "FAILED":
                        failed += 1
                    completed += 1
                    current_completed = completed
                    current_failed = failed
                
                percentage = round((current_completed / total_assets) * 100, 2)
                
                # Emit progress with type field
                emit_progress(
                    "PROCESSING",
                    f"Edited macro {macro_id} ({current_completed}/{total_assets})",
                    record_id,
                    total=total_assets,
                    current=current_completed,
                    percentage=percentage,
                    macro_id=macro_id,
                    failed_records=current_failed,
                    progress_type="MACRO_EDIT"
                )
                            
            except Exception as e:
                async with completed_lock:
                    failed += 1
                    completed += 1
                    
                emit_progress(
                    "ERROR",
                    f"Failed to edit macro {macro_id}",
                    record_id,
                    error=str(e),
                    macro_id=macro_id,
                    progress_type="MACRO_EDIT"
                )

    # Create tasks for parallel processing
    tasks = []
    for i, (page, asset_chunk) in enumerate(zip(pages, asset_chunks)):
        if asset_chunk:
            tasks.append(process_chunk(asset_chunk, page, i))
    
    await asyncio.gather(*tasks)
    
    # Close extra tabs
    for page in pages[1:]:
        await page.close()
    
    # Emit completion with type field
    emit_progress(
        "COMPLETED",
        f"Completed editing {completed}/{total_assets} macros ({failed} failed)",
        record_id,
        total=total_assets,
        current=completed,
        percentage=100.0,
        failed_records=failed,
        numTabs=tabs_num,
        progress_type="MACRO_EDIT"
    )
    
    return {
        "status": "SUCCESS",
        "message": f"Completed editing {completed} macros",
        "failed": failed
    }

async def runMacroEdit(browser, report_id, tabs_num=3, control_state=None):
    """
    Main entry point for editing macros
    Fetches record from DB and processes macro edits
    """    
    try:
        
        emit_progress(
            "FETCHING_RECORD",
            "Fetching report data from database",
            report_id,
            progress_type="MACRO_EDIT"
        )
        
        record = await db.testreports.find_one({"report_id": report_id})
        if not record: 
            return {"status": "FAILED", "error": "Record not found"}
        
        asset_data = record.get("asset_data", [])
        if not asset_data:
            emit_progress(
                "NO_ASSETS",
                "No assets found in record",
                report_id,
                progress_type="MACRO_EDIT"
            )
            return {"status": "SUCCESS", "message": "No assets to edit"}
        
        # Verify assets have macro IDs
        assets_without_ids = [i for i, asset in enumerate(asset_data) if not asset.get("id")]
        if assets_without_ids:
            error_msg = f"Assets missing macro IDs at indices: {assets_without_ids}"
            emit_progress(
                "MISSING_IDS",
                error_msg,
                report_id,
                progress_type="MACRO_EDIT"
            )
            return {"status": "FAILED", "error": error_msg}
        
        emit_progress(
            "STARTING",
            f"Starting macro edit for {len(asset_data)} assets",
            report_id,
            progress_type="MACRO_EDIT"
        )
        
        # Update start time
        await db.testreports.update_one(
            {"_id": record["_id"]},
            {"$set": {"editStartTime": datetime.now(timezone.utc)}}
        )

        # Process macro edits
        edit_result = await handle_macro_edits(
            browser, 
            record, 
            tabs_num=tabs_num, 
            control_state=control_state,
            record_id=report_id
        )
        
        # Update end time
        await db.testreports.update_one(
            {"_id": record["_id"]},
            {"$set": {"editEndTime": datetime.now(timezone.utc)}}
        )
        
        if edit_result.get("status") == "FAILED":
            emit_progress(
                "FAILED",
                "Macro editing failed",
                report_id,
                error=edit_result.get("error"),
                progress_type="MACRO_EDIT"
            )
            return edit_result
        
        emit_progress(
            "COMPLETED",
            "Macro editing completed successfully",
            report_id,
            progress_type="MACRO_EDIT"
        )
        return {"status": "SUCCESS", "recordId": str(report_id), "result": edit_result}

    except Exception as e:
        tb = traceback.format_exc()
        emit_progress(
            "FAILED",
            f"Macro editing failed: {str(e)}",
            report_id,
            error=str(e),
            progress_type="MACRO_EDIT"
        )
        
        # Update end time even on failure
        try:
            await db.testreports.update_one(
                {"report_id": report_id},
                {"$set": {"editEndTime": datetime.now(timezone.utc)}}
            )
        except:
            pass
        
        return {"status": "FAILED", "error": str(e), "traceback": tb}