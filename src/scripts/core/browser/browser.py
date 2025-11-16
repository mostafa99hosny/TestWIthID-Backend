from nodriver import Browser, cdp
from .utils import log
from urllib.parse import urlparse
import traceback, psutil, asyncio, json
from typing import Dict, List, Optional
from datetime import datetime

_browser = None

import numbers

def _unwrap_remote_value(v):
    """
    If v is a dict like {'type':'number','value': 4.5} or {'value': ...},
    return the underlying primitive. Otherwise return v as-is.
    """
    if isinstance(v, dict):
        if 'value' in v and isinstance(v['value'], (str, numbers.Number, bool, type(None))):
            return v['value']
        # some remote shapes: {'type':'number','value':..., 'unserializable_value': None}
        if 'unserializable_value' in v and v.get('unserializable_value') is not None:
            return v.get('unserializable_value')
    return v

def normalize_metrics(raw):
    """
    Accept common raw shapes and return a plain dict {name: value}.
    Handles:
      - dict already: returns shallow-copy (unwrapping remote values)
      - list of [name, {type:, value:...}]    (your observed shape)
      - list of dicts like {'name': 'JSHeapUsedSize', 'value': 12345}
      - None -> {}
    """
    out = {}

    if raw is None:
        return out

    # already a dict -> copy and unwrap values
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[k] = _unwrap_remote_value(v)
        return out

    # list of pairs: [name, value_obj] or tuples
    if isinstance(raw, (list, tuple)):
        # detect list-of-2-tuples like [('memory_used_mb', {'type':'number','value':4.5}), ...]
        all_pairs = all(isinstance(item, (list, tuple)) and len(item) == 2 for item in raw)
        if all_pairs:
            for name, val in raw:
                if isinstance(name, str):
                    out[name] = _unwrap_remote_value(val)
            return out

        # detect list-of-dicts with 'name' & 'value' fields (CDP typical)
        all_name_val = all(isinstance(item, dict) and 'name' in item and 'value' in item for item in raw)
        if all_name_val:
            for item in raw:
                out[item['name']] = _unwrap_remote_value(item['value'])
            return out

        # fallback: try enumerate -> store at numeric keys
        for i, item in enumerate(raw):
            out[str(i)] = _unwrap_remote_value(item)
        return out

    # unknown type -> return empty dict
    return out


async def get_browser(force_new=False):
    global _browser
    if force_new and _browser:
        await closeBrowser()
    
    if not _browser:
        # Simple initialization without complex config
        _browser = await Browser.create(
            headless=False,  # Set to True for headless mode
        )
    
    return _browser

class BrowserResourceTracker:
    """Track resource consumption for browser windows/tabs"""
    
    def __init__(self):
        self._tab_metadata = {}  # tab_id (from page.target.target_id) -> {page, description, created_at}
        self._monitoring = False
        self._monitor_task = None
    
    def _get_tab_id(self, page):
        """Get unique identifier for a page/tab"""
        # Use the target_id which is unique per tab
        if hasattr(page, 'target') and hasattr(page.target, 'target_id'):
            return page.target.target_id
        # Fallback to id() if target_id not available
        return id(page)
    
    def register_tab(self, page, description: str = ""):
        """Register a tab for resource tracking"""
        tab_id = self._get_tab_id(page)
        self._tab_metadata[tab_id] = {
            "page": page,  # Store the actual page object
            "description": description,
            "created_at": datetime.now().isoformat()
        }
        log(f"Registered tab {tab_id} for tracking: {description}", "INFO")
        return page
    
    def unregister_tab(self, page):
        """Unregister a tab from tracking"""
        tab_id = self._get_tab_id(page)
        if tab_id in self._tab_metadata:
            del self._tab_metadata[tab_id]
            log(f"Unregistered tab {tab_id} from tracking", "INFO")
    
    async def get_tab_metrics(self, page) -> Optional[Dict]:
        """Get current metrics for a specific tab"""
        tab_id = self._get_tab_id(page)
        metadata = self._tab_metadata.get(tab_id, {})
        
        # First, try to get basic page info to check if it's accessible
        try:
            type_page = type(page)
            print(json.dumps({"type": str(type_page)}))
            url = await page.evaluate("window.location.href")
            title = await page.evaluate("document.title") 
        except Exception as e:
            # Can't even get URL - page is completely inaccessible
            return {
                "tab_id": tab_id,
                "description": metadata.get("description", "Unknown"),
                "url": "inaccessible",
                "title": "inaccessible",
                "created_at": metadata.get("created_at", "unknown"),
                "error": f"Page inaccessible: {str(e)}",
                "status": "inaccessible"
            }
        
        # Check if it's a Chrome internal page (can't execute JS on these)
        if url and (url.startswith("chrome://") or url.startswith("chrome-extension://") or 
                    url.startswith("about:") or url.startswith("devtools://")):
            return {
                "tab_id": tab_id,
                "description": metadata.get("description", "Unknown"),
                "url": url,
                "title": title or "Chrome Internal Page",
                "created_at": metadata.get("created_at", "unknown"),
                "status": "chrome_internal",
                "metrics": {
                    "memory_mb": 0,
                    "memory_limit_mb": 0,
                    "dom_nodes": 0,
                    "load_time_ms": 0,
                    "dom_ready_ms": 0,
                    "last_updated": datetime.now().isoformat()
                },
                "note": "Chrome internal pages don't expose performance metrics"
            }
        
        try:
            # Get performance metrics from the browser
            # Get performance metrics from the page (this should return a plain serializable value)
            metrics_raw = await page.evaluate("""
            (() => {
              try {
                const mem = performance.memory || {};
                return {
                  memory_used_mb: mem.usedJSHeapSize ? mem.usedJSHeapSize / (1024*1024) : None,
                  url: location.href,
                  title: document.title
                };
              } catch (e) {
                return { error: String(e) };
              }
            })()
            """)

            # Normalize into a plain dict (handles list/dict/remote shapes)
            metrics_dict = normalize_metrics(metrics_raw)

            print("Metrics (raw):", metrics_raw)
            print("Metrics (normalized):", metrics_dict)

            # If evaluate returned a JS error object like {error: "..."} surface it
            if isinstance(metrics_dict.get("error"), str) and not metrics_dict.get("memory_used_mb"):
                return {
                    "tab_id": tab_id,
                    "description": metadata.get("description", "Unknown"),
                    "url": metrics_dict.get("url", url),
                    "title": metrics_dict.get("title", title),
                    "created_at": metadata.get("created_at", "unknown"),
                    "error": metrics_dict.get("error"),
                    "status": "js_error",
                    "metrics": {
                        "memory_mb": 0,
                        "memory_limit_mb": 0,
                        "dom_nodes": 0,
                        "load_time_ms": 0,
                        "dom_ready_ms": 0,
                        "last_updated": datetime.now().isoformat()
                    }
                }

            # Try to get CDP (Chrome DevTools Protocol) metrics for more detailed info
            cdp_metrics = None
            try:
                # Many CDP wrappers expect the string 'Performance.getMetrics' (adjust if nodriver has helper)
                cdp_resp = None
                try:
                    # prefer a plain command form (works in pyppeteer/playwright raw cdp)
                    cdp_resp = await page.send('Performance.getMetrics')
                except Exception:
                    # some wrappers require different calling style; try the helper you used
                    try:
                        cdp_resp = await page.send(cdp.performance.get_metrics())
                    except Exception:
                        cdp_resp = None

                # cdp_resp might be like {'metrics': [{name:, value:}, ...]} or a raw list
                raw_metrics_list = None
                if isinstance(cdp_resp, dict) and 'metrics' in cdp_resp:
                    raw_metrics_list = cdp_resp['metrics']
                elif isinstance(cdp_resp, list):
                    raw_metrics_list = cdp_resp
                elif isinstance(cdp_resp, dict) and 'result' in cdp_resp and isinstance(cdp_resp['result'], dict):
                    raw_metrics_list = cdp_resp['result'].get('metrics') or cdp_resp['result'].get('value')

                if raw_metrics_list:
                    cdp_metrics = normalize_metrics(raw_metrics_list)

            except Exception as cdp_error:
                log(f"Could not get CDP metrics for tab {tab_id}: {cdp_error}", "DEBUG")

            # Build result using normalized values (safe .get usage)
            result = {
                "tab_id": tab_id,
                "description": metadata.get("description", "Unknown"),
                "url": metrics_dict.get("url", url),
                "title": metrics_dict.get("title", title),
                "created_at": metadata.get("created_at", "unknown"),
                "status": "success",
                "metrics": {
                    "memory_mb": round(metrics_dict.get("memory_used_mb", 0) or 0, 2),
                    "memory_limit_mb": round(metrics_dict.get("memory_limit_mb", 0) or 0, 2),
                    "dom_nodes": int(metrics_dict.get("dom_nodes", 0) or 0),
                    "load_time_ms": round(metrics_dict.get("load_time_ms", 0) or 0, 2),
                    "dom_ready_ms": round(metrics_dict.get("dom_ready_ms", 0) or 0, 2),
                    "last_updated": datetime.now().isoformat()
                }
            }

            # Add CDP metrics if available (also normalized)
            if cdp_metrics:
                # safe get with defaults
                result["cdp_metrics"] = {
                    "documents": int(cdp_metrics.get("Documents", 0) or 0),
                    "frames": int(cdp_metrics.get("Frames", 0) or 0),
                    "js_event_listeners": int(cdp_metrics.get("JSEventListeners", 0) or 0),
                    "nodes": int(cdp_metrics.get("Nodes", 0) or 0),
                    "layout_count": int(cdp_metrics.get("LayoutCount", 0) or 0),
                    "recalc_style_count": int(cdp_metrics.get("RecalcStyleCount", 0) or 0),
                    "js_heap_used_mb": round((cdp_metrics.get("JSHeapUsedSize", 0) or 0) / (1024 * 1024), 2),
                    "js_heap_total_mb": round((cdp_metrics.get("JSHeapTotalSize", 0) or 0) / (1024 * 1024), 2)
                }



            
            # Handle case where evaluate returns None (shouldn't happen now, but just in case)
            if metrics_dict is None:
                log(f"Tab {tab_id}: evaluate returned None despite URL check", "WARN")
                return {
                    "tab_id": tab_id,
                    "description": metadata.get("description", "Unknown"),
                    "url": url,
                    "title": title,
                    "created_at": metadata.get("created_at", "unknown"),
                    "error": "evaluate returned None unexpectedly",
                    "status": "metrics_unavailable",
                    "metrics": {
                        "memory_mb": 0,
                        "memory_limit_mb": 0,
                        "dom_nodes": 0,
                        "load_time_ms": 0,
                        "dom_ready_ms": 0,
                        "last_updated": datetime.now().isoformat()
                    }
                }
            
            # Check if JS returned an error
            if isinstance(metrics_dict, dict) and "error" in metrics_dict and not metrics_dict.get("memory_used_mb"):
                return {
                    "tab_id": tab_id,
                    "description": metadata.get("description", "Unknown"),
                    "url": metrics_dict.get("url", url),
                    "title": metrics_dict.get("title", title),
                    "created_at": metadata.get("created_at", "unknown"),
                    "error": metrics_dict.get("error"),
                    "status": "js_error",
                    "metrics": {
                        "memory_mb": 0,
                        "memory_limit_mb": 0,
                        "dom_nodes": 0,
                        "load_time_ms": 0,
                        "dom_ready_ms": 0,
                        "last_updated": datetime.now().isoformat()
                    }
                }
            
            # Try to get CDP (Chrome DevTools Protocol) metrics for more detailed info
            cdp_metrics = None
            try:
                # Use CDP to get process metrics
                result = await page.send(cdp.performance.get_metrics())
                if result:
                    cdp_metrics = {}
                    for metric in result:
                        cdp_metrics[metric.name] = metric.value
            except Exception as cdp_error:
                log(f"Could not get CDP metrics for tab {tab_id}: {cdp_error}", "DEBUG")
            
            # Successfully got metrics
            result = {
                "tab_id": tab_id,
                "url": metrics_dict.get("url", url),
                "title": metrics_dict.get("title", title),
                "status": "success",
                "metrics": {
                    "memory_mb": round(metrics_dict.get("memory_used_mb", 0), 2),
                    "memory_limit_mb": round(metrics_dict.get("memory_limit_mb", 0), 2),
                    "dom_nodes": metrics_dict.get("dom_nodes", 0),
                    "load_time_ms": round(metrics_dict.get("load_time_ms", 0), 2),
                    "dom_ready_ms": round(metrics_dict.get("dom_ready_ms", 0), 2),
                    "last_updated": datetime.now().isoformat()
                }
            }
            
            # Add CDP metrics if available
            if cdp_metrics:
                result["cdp_metrics"] = {
                    "documents": int(cdp_metrics.get("Documents", 0)),
                    "frames": int(cdp_metrics.get("Frames", 0)),
                    "js_event_listeners": int(cdp_metrics.get("JSEventListeners", 0)),
                    "nodes": int(cdp_metrics.get("Nodes", 0)),
                    "layout_count": int(cdp_metrics.get("LayoutCount", 0)),
                    "recalc_style_count": int(cdp_metrics.get("RecalcStyleCount", 0)),
                    "js_heap_used_mb": round(cdp_metrics.get("JSHeapUsedSize", 0) / (1024 * 1024), 2),
                    "js_heap_total_mb": round(cdp_metrics.get("JSHeapTotalSize", 0) / (1024 * 1024), 2)
                }
            
            return result
            
        except Exception as e:
            log(f"Error getting metrics for tab {tab_id}: {e}", "WARN")
            import traceback
            log(f"Traceback: {traceback.format_exc()}", "DEBUG")
            
            return {
                "tab_id": tab_id,
                "description": metadata.get("description", "Unknown"),
                "url": url if 'url' in locals() else "unknown",
                "title": title if 'title' in locals() else "unknown",
                "error": str(e),
                "status": "error",
                "created_at": metadata.get("created_at", "unknown"),
                "metrics": {
                    "memory_mb": 0,
                    "last_updated": datetime.now().isoformat()
                }
            }
    
    async def get_all_metrics(self) -> List[Dict]:
        """Get metrics for all browser tabs"""
        try:
            browser = await get_browser()
            all_tabs = browser.tabs
            
            results = []
            for idx, page in enumerate(all_tabs):
                metrics = await self.get_tab_metrics(page)
                if metrics:
                    # Add index for reference
                    metrics["tab_index"] = idx
                    results.append(metrics)
            
            return results
        except Exception as e:
            log(f"Error getting all metrics: {e}", "ERROR")
            import traceback
            log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return []
    
    async def sync_metadata(self):
        """Clean up metadata for closed tabs"""
        try:
            browser = await get_browser()
            current_tabs = browser.tabs
            
            # Create a set of current tab IDs
            current_tab_ids = {self._get_tab_id(tab) for tab in current_tabs}
            
            # Remove metadata for tabs that no longer exist
            removed_count = 0
            for tab_id in list(self._tab_metadata.keys()):  # FIX: Iterate over keys (tab_ids)
                if tab_id not in current_tab_ids:  # FIX: Compare tab_ids
                    log(f"Tab {tab_id} no longer exists, removing metadata", "INFO")
                    del self._tab_metadata[tab_id]
                    removed_count += 1
            
            return {
                "removed": removed_count,
                "total_tracked": len(self._tab_metadata),
                "total_tabs": len(current_tabs)
            }
            
        except Exception as e:
            log(f"Error syncing metadata: {e}", "ERROR")
            import traceback
            log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return {"error": str(e)}
    
    async def get_browser_process_metrics(self) -> Dict:
        """Get overall browser process metrics"""
        try:
            browser = await get_browser()
            
            # nodriver stores browser process info differently
            # Try to find the Chrome/Chromium process
            browser_process = None
            
            # Method 1: Check if browser has a process attribute
            if hasattr(browser, 'process') and browser.process:
                browser_process = psutil.Process(browser.process.pid)
            # Method 2: Check browser config
            elif hasattr(browser, 'config') and hasattr(browser.config, 'browser_process_pid'):
                browser_process = psutil.Process(browser.config.browser_process_pid)
            # Method 3: Search for Chrome/Chromium processes
            else:
                # Find Chrome/Chromium process by name
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        name = proc.info['name'].lower()
                        cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                        
                        # Look for Chrome/Chromium with remote-debugging-port
                        if ('chrome' in name or 'chromium' in name) and 'remote-debugging-port' in cmdline:
                            browser_process = proc
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            if browser_process:
                try:
                    # Get all child processes (tabs, GPU process, etc.)
                    children = browser_process.children(recursive=True)
                    
                    # Get metrics
                    total_cpu = browser_process.cpu_percent(interval=0.1)
                    total_memory = browser_process.memory_info().rss / (1024 * 1024)  # MB
                    
                    # Aggregate child process metrics
                    child_cpu = 0
                    child_memory = 0
                    for child in children:
                        try:
                            child_cpu += child.cpu_percent(interval=0.1)
                            child_memory += child.memory_info().rss / (1024 * 1024)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    return {
                        "browser_pid": browser_process.pid,
                        "browser_cpu_percent": round(total_cpu, 2),
                        "browser_memory_mb": round(total_memory, 2),
                        "total_cpu_percent": round(total_cpu + child_cpu, 2),
                        "total_memory_mb": round(total_memory + child_memory, 2),
                        "child_processes": len(children),
                        "timestamp": datetime.now().isoformat()
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    log(f"Process access error: {e}", "WARN")
                    return {
                        "error": f"Could not access browser process: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                # Fallback: just count tabs
                tab_count = len(browser.tabs) if hasattr(browser, 'tabs') else 0
                return {
                    "error": "Could not locate browser process",
                    "tab_count": tab_count,
                    "note": "Process-level metrics unavailable, but browser is running",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            log(f"Error getting browser process metrics: {e}", "ERROR")
            tb = traceback.format_exc()
            return {
                "error": str(e),
                "traceback": tb,
                "timestamp": datetime.now().isoformat()
            }
    
    async def start_monitoring(self, interval: int = 5):
        """Start periodic monitoring of all tabs"""
        if self._monitoring:
            log("Monitoring already active", "WARN")
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        log(f"Started resource monitoring (interval: {interval}s)", "INFO")
    
    async def stop_monitoring(self):
        """Stop periodic monitoring"""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        log("Stopped resource monitoring", "INFO")
    
    async def _monitor_loop(self, interval: int):
        """Internal monitoring loop"""
        while self._monitoring:
            try:
                # Clean up metadata for closed tabs
                await self.sync_metadata()
                
                # Update metrics for all tabs
                await self.get_all_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log(f"Error in monitoring loop: {e}", "ERROR")
                await asyncio.sleep(interval)


# Global tracker instance
_resource_tracker = BrowserResourceTracker()


async def get_resource_tracker():
    """Get the global resource tracker instance"""
    return _resource_tracker


# Enhanced navigation function with tracking
async def navigate_with_tracking(url: str, description: str = ""):
    """Navigate to URL and register for resource tracking"""
    page = await navigate(url)
    
    tracker = await get_resource_tracker()
    tracker.register_tab(page, description or f"Navigation: {url}")
    
    return page


# Enhanced new_window function with tracking
async def new_window_with_tracking(url: str = None, description: str = ""):
    """Create new window and register for resource tracking"""
    page = await new_window(url)
    
    tracker = await get_resource_tracker()
    tracker.register_tab(page, description or f"New window: {url or 'blank'}")
    
    return page


async def create_new_browser_window(description: str = ""):
    """Create new browser window and auto-register for tracking"""
    browser = await get_browser()
    new_page = await browser.get("https://qima.taqeem.sa/", new_window=True)
    
    url = await new_page.evaluate('window.location.href')
    log(f"Created new browser window with URL: {url}", "INFO")
    
    # Auto-register for resource tracking
    tracker = await get_resource_tracker()
    tracker.register_tab(new_page, description or f"Browser window: {url}")
    log(f"Auto-registered window for resource tracking", "INFO")
    
    return new_page


def _is_valid_http_url(url: str) -> bool:
    try:
        parts = urlparse(url)
        return parts.scheme in ("http", "https") and bool(parts.netloc)
    except Exception:
        return False


async def get_page():
    browser = await get_browser()
    return browser.main_tab


async def navigate(url: str):
    def _sanitize(u: str) -> str:
        return (u or "").strip().strip('"\\' + "'")

    url = _sanitize(url)
    browser = await get_browser()

    if not _is_valid_http_url(url):
        log(f"Invalid URL -> '{url}'", "ERR")
        page = await browser.new_page()
        return page

    # Try once, then restart browser and retry once more if transport fails
    for attempt in range(2):
        try:
            return await browser.get(url)
        except Exception as e:
            log(f"browser.get() failed (try {attempt+1}/2): {e}", "WARN")
            try:
                page = await browser.new_page()
                await page.evaluate("url => { window.location.href = url; }", url)
                return page
            except Exception as e2:
                log(f"fallback window.location failed: {e2}", "WARN")
                if attempt == 0:
                    # restart browser and retry
                    try:
                        await closeBrowser()
                    except Exception:
                        pass
                    # get_browser() will recreate
                    browser = await get_browser()
                else:
                    # give up with a blank page
                    try:
                        return await browser.new_page()
                    except Exception:
                        raise


async def set_page(page):
    # For compatibility - not needed with nodriver
    pass


async def closeBrowser():
    global _browser
    if _browser:
        try:
            await _browser.stop()
        except Exception as e:
            print(f"Warning: Error closing browser: {e}")
        finally:
            _browser = None


async def is_browser_open():
    """Check if browser instance exists, is active, and user is logged in"""
    global _browser
    if _browser is None:
        return {"status": "FAILED", "error": "No browser instance", "browserOpen": False}
    
    try:
        page = _browser.main_tab
        url = await page.evaluate("window.location.href")
        current_url = url.lower()
        
        # URLs that definitively indicate NOT logged in
        non_logged_in_urls = [
            "sso.taqeem.gov.sa/realms/rel_taqeem/login-actions/authenticate",
            "sso.taqeem.gov.sa/realms/rel_taqeem/protocol/openid-connect/auth",
            "/login-actions/authenticate",
            "/protocol/openid-connect/auth"
        ]
        
        # If we're on any authentication URL, we're definitely not logged in
        if any(auth_url in current_url for auth_url in non_logged_in_urls):
            return {"status": "FAILED", "error": "User not logged in", "browserOpen": True}
            
        # If browser is responsive and we're NOT on auth URLs, assume logged in
        return {"status": "SUCCESS", "message": "User is logged in", "browserOpen": True}
        
    except Exception as e:
        # Browser instance exists but is not actually running
        _browser = None
        return {"status": "FAILED", "error": str(e), "browserOpen": False}


async def wait_for_element(page, selector, timeout=30):
    """Wait for element with timeout"""
    try:
        element = await page.select(selector, timeout=timeout)
        return element
    except Exception as e:
        print(f"Warning: Element not found: {selector} - {e}")
        return None


async def new_window(url: str | None = None):
    if url:
        return await navigate(url)
    browser = await get_browser()
    return await browser.new_page()