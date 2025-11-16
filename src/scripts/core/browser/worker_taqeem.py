import asyncio
import sys
import json
import traceback
import platform
from scripts.loginFlow.login import startLogin, submitOtp
from .browser import closeBrowser, get_browser, create_new_browser_window
from scripts.submission.validateReportExistence import validate_report
from scripts.delete.reportDelete import delete_report_flow
from scripts.submission.grabMacroIds import get_all_macro_ids_parallel
from .browser import get_resource_tracker

if platform.system().lower() == "windows":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Task control management
_task_controls = {}
_active_tasks = {}  # Track running tasks

class TaskStoppedException(Exception):
    """Raised when task is stopped"""
    pass

def create_control_state(task_id, batch_id=None):
    """Create a new control state for a task"""
    # Normalize batch_id to string for consistent comparison
    batch_id = str(batch_id) if batch_id is not None else None
    
    _task_controls[task_id] = {
        "paused": False,
        "stopped": False,
        "batch_id": batch_id
    }
    print(f"[PY DEBUG] Created control state: task_id={task_id}, batch_id={batch_id} (type: {type(batch_id)})", file=sys.stderr)
    return _task_controls[task_id]

def get_control_state(task_id):
    """Get control state for a task"""
    return _task_controls.get(task_id)

def cleanup_control_state(task_id):
    """Remove control state when task completes"""
    if task_id in _task_controls:
        del _task_controls[task_id]
    if task_id in _active_tasks:
        del _active_tasks[task_id]

async def check_control(state):
    """Check if we should pause or stop"""
    print(f"[PY DEBUG CHECK_CONTROL] Checking state: paused={state.get('paused')}, stopped={state.get('stopped')}", file=sys.stderr)
    
    if state.get("stopped"):
        print(f"[PY DEBUG CHECK_CONTROL] Task is STOPPED - raising exception", file=sys.stderr)
        raise TaskStoppedException("Task was stopped by user")
    
    was_paused = False
    while state.get("paused"):
        if not was_paused:
            print(f"[PY DEBUG CHECK_CONTROL] Task is PAUSED - entering wait loop", file=sys.stderr)
            was_paused = True
        await asyncio.sleep(0.5)
        if state.get("stopped"):
            print(f"[PY DEBUG CHECK_CONTROL] Task was stopped while paused", file=sys.stderr)
            raise TaskStoppedException("Task was stopped by user")
    
    if was_paused:
        print(f"[PY DEBUG CHECK_CONTROL] Task RESUMED - exiting wait loop", file=sys.stderr)

async def handle_control_command(cmd):
    """Handle control commands (pause, resume, stop)"""
    try:
        action = cmd.get("action")
        batch_id = str(cmd.get("batchId")) if cmd.get("batchId") is not None else None
        
        print(f"[PY DEBUG] Control command received:", file=sys.stderr)
        print(f"[PY DEBUG]   action: {action}", file=sys.stderr)
        print(f"[PY DEBUG]   batchId: {batch_id}", file=sys.stderr)
        
        # Debug: Print all current control states
        print(f"[PY DEBUG] Current _task_controls:", file=sys.stderr)
        for task_id, state in _task_controls.items():
            print(f"[PY DEBUG]   {task_id}: batch_id={state.get('batch_id')}, paused={state.get('paused')}, stopped={state.get('stopped')}", file=sys.stderr)
        
        # Find control state by batch_id
        target_state = None
        target_task_id = None
        
        for task_id, state in _task_controls.items():
            state_batch_id = str(state.get("batch_id")) if state.get("batch_id") is not None else None
            print(f"[PY DEBUG] Comparing: task={task_id}, state_batch_id={state_batch_id}, looking_for={batch_id}", file=sys.stderr)
            
            if state_batch_id == batch_id:
                target_state = state
                target_task_id = task_id
                print(f"[PY DEBUG] MATCH FOUND! task_id={task_id}", file=sys.stderr)
                break
        
        if not target_state:
            error_msg = f"No active task found for batch {batch_id}"
            print(f"[PY DEBUG] ERROR: {error_msg}", file=sys.stderr)
            result = {
                "status": "FAILED", 
                "error": error_msg,
                "commandId": cmd.get("commandId"),
                "debug": {
                    "available_tasks": list(_task_controls.keys()),
                    "available_batch_ids": [str(s.get("batch_id")) for s in _task_controls.values()]
                }
            }
            print(json.dumps(result), flush=True)
            return
        
        print(f"[PY DEBUG] Found target_state for task_id={target_task_id}", file=sys.stderr)
        
        if action == "pause":
            print(f"[PY DEBUG] Setting paused=True for task {target_task_id}", file=sys.stderr)
            target_state["paused"] = True
            result = {
                "status": "PAUSED", 
                "message": "Task paused",
                "batchId": batch_id,
                "commandId": cmd.get("commandId")
            }
            
        elif action == "resume":
            print(f"[PY DEBUG] Setting paused=False for task {target_task_id}", file=sys.stderr)
            target_state["paused"] = False
            result = {
                "status": "RESUMED", 
                "message": "Task resumed",
                "batchId": batch_id,
                "commandId": cmd.get("commandId")
            }
            
        elif action == "stop":
            print(f"[PY DEBUG] Setting stopped=True for task {target_task_id}", file=sys.stderr)
            target_state["stopped"] = True
            target_state["paused"] = False
            
            # Close all tabs except the main page
            try:
                browser = await get_browser()
                pages = browser.tabs
                if len(pages) > 1:
                    for page in pages[1:]:
                        try:
                            await page.close()
                        except Exception as e:
                            print(f"Warning: Failed to close tab: {e}", file=sys.stderr)
                    print(f"Closed {len(pages) - 1} additional tabs", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Error closing tabs: {e}", file=sys.stderr)
            
            result = {
                "status": "STOPPED", 
                "message": "Task stopped",
                "batchId": batch_id,
                "commandId": cmd.get("commandId")
            }
        
        print(f"[PY DEBUG] Sending result: {result}", file=sys.stderr)
        print(json.dumps(result), flush=True)
        
        # Verify the state was actually changed
        print(f"[PY DEBUG] After change, target_state is now: paused={target_state.get('paused')}, stopped={target_state.get('stopped')}", file=sys.stderr)
        
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[PY DEBUG] Exception in handle_control_command: {e}", file=sys.stderr)
        print(f"[PY DEBUG] Traceback: {tb}", file=sys.stderr)
        result = {
            "status": "FAILED", 
            "error": str(e), 
            "traceback": tb,
            "commandId": cmd.get("commandId")
        }
        print(json.dumps(result), flush=True)

async def handle_get_resource_metrics(cmd):
    """Handle request for resource metrics"""
    try:
        tracker = await get_resource_tracker()
        tab_id = cmd.get("tabId")
        
        if tab_id:
            # Get metrics for specific tab
            metrics = await tracker.get_tab_metrics(tab_id)
            if metrics:
                result = {
                    "status": "SUCCESS",
                    "data": metrics,
                    "commandId": cmd.get("commandId")
                }
            else:
                result = {
                    "status": "FAILED",
                    "error": f"Tab {tab_id} not found",
                    "commandId": cmd.get("commandId")
                }
        else:
            # Get metrics for all tabs
            all_metrics = await tracker.get_all_metrics()
            browser_metrics = await tracker.get_browser_process_metrics()
            
            result = {
                "status": "SUCCESS",
                "data": {
                    "tabs": all_metrics,
                    "browser": browser_metrics,
                    "total_tabs": len(all_metrics)
                },
                "commandId": cmd.get("commandId")
            }
        
        print(json.dumps(result), flush=True)
        
    except Exception as e:
        tb = traceback.format_exc()
        result = {
            "status": "FAILED",
            "error": str(e),
            "traceback": tb,
            "commandId": cmd.get("commandId")
        }
        print(json.dumps(result), flush=True)


async def run_edit_macros_task(cmd, browser):
    """Run edit_macros as a background task"""
    report_id = cmd.get("reportId")
    tabs_num = cmd.get("tabsNum", 3)
    command_id = cmd.get("commandId")
    
    # Create control state for this task
    task_id = f"edit_macros_{report_id}"
    control_state = create_control_state(task_id, report_id)
    
    try:
        from scripts.submission.macroFiller import runMacroEdit
        
        result = await runMacroEdit(
            browser=browser,
            report_id=report_id,
            tabs_num=tabs_num,
            control_state=control_state,
        )
        result["commandId"] = command_id
        print(json.dumps(result), flush=True)
        
    except TaskStoppedException as e:
        result = {
            "status": "STOPPED",
            "message": str(e),
            "commandId": command_id
        }
        print(json.dumps(result), flush=True)
        
    except Exception as e:
        tb = traceback.format_exc()
        result = {
            "status": "FAILED",
            "error": str(e),
            "traceback": tb,
            "commandId": command_id
        }
        print(json.dumps(result), flush=True)
        
    finally:
        # Cleanup control state
        cleanup_control_state(task_id)

async def command_handler():
    """Main command handler for the worker"""
    loop = asyncio.get_running_loop()
    
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        
        try:
            cmd = json.loads(line.strip())
            action = cmd.get("action")
            
            print(f"[PY DEBUG] RAW COMMAND RECEIVED: {cmd}", file=sys.stderr)
            print(f"[PY] Received action: {action}", file=sys.stderr)
            
            
            if action == "login":
                browser = await get_browser(force_new=True)
                page = await browser.get(
                    "https://sso.taqeem.gov.sa/realms/REL_TAQEEM/protocol/openid-connect/auth"
                    "?client_id=cli-qima-valuers&redirect_uri=https%3A%2F%2Fqima.taqeem.sa%2Fkeycloak%2Flogin%2Fcallback"
                    "&scope=openid&response_type=code"
                )
                result = await startLogin(page, cmd.get("email", ""), cmd.get("password", ""), cmd.get("method"))
                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)
                
            elif action == "otp":
                browser = await get_browser()
                if not browser or not browser.main_tab:
                    result = {
                        "status": "FAILED", 
                        "error": "No active browser session. Please login first.",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    continue
                page = browser.main_tab
                result = await submitOtp(page, cmd.get("otp", ""), cmd.get("recordId"))
                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)

            elif action == "get_resource_metrics":
                from .browser import get_resource_tracker
                
                tracker = await get_resource_tracker()
                tab_id = cmd.get("tabId")
                
                try:
                    if tab_id:
                        # Get metrics for specific tab
                        metrics = await tracker.get_tab_metrics(tab_id)
                        if metrics:
                            result = {
                                "status": "SUCCESS",
                                "data": metrics,
                                "commandId": cmd.get("commandId")
                            }
                        else:
                            result = {
                                "status": "FAILED",
                                "error": f"Tab {tab_id} not found",
                                "commandId": cmd.get("commandId")
                            }
                    else:
                        # Get metrics for all tabs
                        all_metrics = await tracker.get_all_metrics()
                        browser_metrics = await tracker.get_browser_process_metrics()
                        
                        result = {
                            "status": "SUCCESS",
                            "data": {
                                "tabs": all_metrics,
                                "browser": browser_metrics,
                                "total_tabs": len(all_metrics)
                            },
                            "commandId": cmd.get("commandId")
                        }
                    
                    print(json.dumps(result), flush=True)
                    
                except Exception as e:
                    tb = traceback.format_exc()
                    result = {
                        "status": "FAILED",
                        "error": str(e),
                        "traceback": tb,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)

            elif action == "start_resource_monitoring":
                from .browser import get_resource_tracker
                
                tracker = await get_resource_tracker()
                interval = cmd.get("interval", 5)
                
                try:
                    await tracker.start_monitoring(interval)
                    result = {
                        "status": "SUCCESS",
                        "message": f"Resource monitoring started with {interval}s interval",
                        "interval": interval,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    
                except Exception as e:
                    tb = traceback.format_exc()
                    result = {
                        "status": "FAILED",
                        "error": str(e),
                        "traceback": tb,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)

            elif action == "stop_resource_monitoring":
                from .browser import get_resource_tracker
                
                tracker = await get_resource_tracker()
                
                try:
                    await tracker.stop_monitoring()
                    result = {
                        "status": "SUCCESS",
                        "message": "Resource monitoring stopped",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    
                except Exception as e:
                    tb = traceback.format_exc()
                    result = {
                        "status": "FAILED",
                        "error": str(e),
                        "traceback": tb,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)

            elif action == "validate_excel_data":
                result = await validate_report(cmd)
                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)

            elif action == "new_window":
                # Create a new browser window
                new_page = await create_new_browser_window()
                result = {
                    "status": "SUCCESS",
                    "message": "New browser window created successfully",
                    "commandId": cmd.get("commandId"),
                    "data": {
                        "url": await new_page.evaluate("window.location.href")
                    }
                }
                print(json.dumps(result), flush=True)

            elif action == "create_assets":
                browser = await get_browser()
                if not browser:
                    result = {
                        "status": "FAILED", 
                        "error": "No active browser session. Please login first.",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    continue
                
                report_id = cmd.get("reportId")
                macro_count = cmd.get("macroCount")
                tabs_num = cmd.get("tabsNum", 3)
                batch_id = cmd.get("batchId")
                
                if not report_id:
                    result = {
                        "status": "FAILED",
                        "error": "Missing required parameter: reportId",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    continue
                
                if not macro_count or macro_count <= 0:
                    result = {
                        "status": "FAILED",
                        "error": "Missing or invalid required parameter: macroCount",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    continue
                
                task_id = f"create_assets_{report_id}_{batch_id}"
                control_state = create_control_state(task_id, batch_id)
                
                try:
                    from scripts.submission.formSteps import form_steps
                    from scripts.submission.createAssets import create_macros_multi_tab
                    field_map = form_steps[1]["field_map"]
                    field_types = form_steps[1]["field_types"]
                    
                    macro_data_template = cmd.get("macroData", {})
                    
                    result = await create_macros_multi_tab(
                        browser=browser,
                        report_id=report_id,
                        macro_count=macro_count,
                        macro_data_template=macro_data_template,
                        field_map=field_map,
                        field_types=field_types,
                        max_tabs=tabs_num,
                        batch_size=10,
                        control_state=control_state
                    )
                    
                    result["commandId"] = cmd.get("commandId")
                    print(json.dumps(result), flush=True)
                    
                except TaskStoppedException as e:
                    result = {
                        "status": "STOPPED",
                        "message": str(e),
                        "reportId": report_id,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    
                except Exception as e:
                    tb = traceback.format_exc()
                    result = {
                        "status": "FAILED",
                        "error": str(e),
                        "traceback": tb,
                        "reportId": report_id,
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    
                finally:
                    cleanup_control_state(task_id)

            elif action == "delete_report":
                browser = await get_browser()
                result = await delete_report_flow(
                    report_id=cmd.get("reportId"),
                )
                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)

            elif action == "grab_ids":
                browser = await get_browser()
                result = await get_all_macro_ids_parallel(
                    browser=browser,
                    report_id=cmd.get("reportId"),
                    tabs_num=cmd.get("tabsNum", 3)
                )
                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)

            elif action == "edit_macros":
                browser = await get_browser()
                if not browser:
                    result = {
                        "status": "FAILED", 
                        "error": "No active browser session. Please login first.",
                        "commandId": cmd.get("commandId")
                    }
                    print(json.dumps(result), flush=True)
                    continue
                
                # Run as background task so command handler can continue processing
                print(f"[PY DEBUG] Starting edit_macros task in background", file=sys.stderr)
                task = asyncio.create_task(run_edit_macros_task(cmd, browser))
                _active_tasks[cmd.get("reportId")] = task
                
                # Send immediate acknowledgment
                ack_result = {
                    "status": "STARTED",
                    "message": "Macro editing started",
                    "commandId": cmd.get("commandId")
                }
                print(json.dumps(ack_result), flush=True)

            elif action == "check_macro_status":
                from scripts.submission.checkMacroStatus import RunCheckMacroStatus
                browser = await get_browser()
                report_id = cmd.get("reportId")
                tabs_num = cmd.get("tabsNum", 3)

                result = await RunCheckMacroStatus(
                    browser=browser,
                    report_id=report_id,
                    tabs_num=tabs_num   
                )

                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)

            elif action == "half_check_macro_status":
                from scripts.submission.checkMacroStatus import RunHalfCheckMacroStatus
                browser = await get_browser()
                report_id = cmd.get("reportId")
                tabs_num = cmd.get("tabsNum", 3)

                result = await RunHalfCheckMacroStatus(
                    browser=browser,
                    report_id=report_id,
                    tabs_num=tabs_num   
                )

                result["commandId"] = cmd.get("commandId")
                print(json.dumps(result), flush=True)
                
            elif action == "handle_cancelled_report":
                from scripts.delete.cancelledReportHandler import handle_cancelled_report
                report_id = cmd.get("reportId")

                result = await handle_cancelled_report(report_id)
                result["commandId"] = cmd.get("commandId")

                print(json.dumps(result), flush=True)

            elif action == "check_browser":
                from .browser import is_browser_open
                
                result = await is_browser_open()
                result["commandId"] = cmd.get("commandId")
                
                print(json.dumps(result), flush=True)

            elif action == "close":
                await closeBrowser()
                result = {
                    "status": "SUCCESS",
                    "message": "Browser closed successfully",
                    "commandId": cmd.get("commandId")
                }
                print(json.dumps(result), flush=True)
                break
                
            elif action == "ping":
                result = {
                    "status": "SUCCESS",
                    "message": "pong",
                    "commandId": cmd.get("commandId")
                }
                print(json.dumps(result), flush=True)
                
            elif action in ["pause", "resume", "stop"]:
                print(f"[PY DEBUG] Processing control command: {action}", file=sys.stderr)
                await handle_control_command(cmd)
                
            else:
                result = {
                    "status": "FAILED", 
                    "error": f"Unknown action: {action}",
                    "supported_actions": ["login", "otp", "validate_excel_data", "create_assets", "close", "ping", "pause", "resume", "stop"],
                    "commandId": cmd.get("commandId")
                }
                print(json.dumps(result), flush=True)
                
        except json.JSONDecodeError as e:
            error_response = {
                "status": "FAILED",
                "error": f"Invalid JSON: {str(e)}",
                "received": line.strip()
            }
            print(json.dumps(error_response), flush=True)
        except Exception as e:
            tb = traceback.format_exc()
            error_response = {
                "status": "FAILED",
                "error": f"Command handler error: {str(e)}",
                "traceback": tb
            }
            print(json.dumps(error_response), flush=True)

async def main():
    try:
        await command_handler()
    except Exception as e:
        print(json.dumps({"status": "FATAL", "error": str(e)}), flush=True)
    finally:
        await closeBrowser()

if __name__ == "__main__":
    asyncio.run(main())