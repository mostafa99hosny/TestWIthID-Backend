import asyncio, time, os, zipfile
from datetime import datetime

def log(msg: str, level: str = "INFO"):
    stamp = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO":"ℹ️", "OK":"✅", "ERR":"❌", "STEP":"👉"}
    print(f"{icons.get(level,'ℹ️')} [{stamp}] {msg}", flush=True)

async def wait_for_element(page, selector: str, timeout: float = 30.0, interval: float = 0.5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            el = await page.find(selector)
            if el:
                return el
        except Exception:
            pass
        await asyncio.sleep(interval)
    return None

def zip_folder(folder_path: str, out_zip_path: str):
    with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder_path):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, folder_path)
                z.write(full, arcname=rel)
    return out_zip_path

