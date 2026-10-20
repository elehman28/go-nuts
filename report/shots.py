"""Take screenshots of the running Go Nuts app with headless Chrome (Chrome DevTools Protocol).
Usage: python shots.py OUT_DIR   (app must be running on http://localhost:8501)"""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE = Path(sys.argv[1]).parent / "chrome-profile"


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        my = self.n
        await self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my:
                return msg.get("result", {})

    async def js(self, expr, wait=0.0):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if wait:
            await asyncio.sleep(wait)
        return r.get("result", {}).get("value")

    async def shot(self, name, full=False):
        params = {"format": "png"}
        if full:
            m = await self.call("Page.getLayoutMetrics")
            h = min(int(m["cssContentSize"]["height"]), 4000)
            params["clip"] = {"x": 0, "y": 0, "width": 1280, "height": h, "scale": 1}
            params["captureBeyondViewport"] = True
        data = (await self.call("Page.captureScreenshot", **params))["data"]
        (OUT / f"{name}.png").write_bytes(base64.b64decode(data))
        print("saved", name)


WAIT_APP = """(async()=>{for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,500));
  if(document.querySelector('.gn-brand') && !document.querySelector('[data-testid=stStatusWidget]'))return true;}return false})()"""
CLICK_TAB = """(async(t)=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.toUpperCase().includes(t));
  b&&b.click();await new Promise(r=>setTimeout(r,2500));window.scrollTo(0,0);return !!b})"""
CLICK_BUTTON = """(async(t)=>{const b=[...document.querySelectorAll('button')].filter(x=>x.innerText.trim().toUpperCase().startsWith(t)
  && x.getBoundingClientRect().width>10).pop(); b&&b.click(); for(let i=0;i<40;i++){await new Promise(r=>setTimeout(r,500));
  if(!document.querySelector('[data-testid=stStatusWidget]'))break;} await new Promise(r=>setTimeout(r,1200)); return !!b})"""
SCROLL_TO = """((sel,txt)=>{const e=[...document.querySelectorAll(sel)].find(x=>!txt||x.innerText.includes(txt));
  if(e){e.scrollIntoView({block:'start'});window.scrollBy(0,-20);} return !!e})"""


async def main():
    chrome = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9333", f"--user-data-dir={PROFILE}",
                               "--hide-scrollbars", "--window-size=1280,900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                pages = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                break
            except OSError:
                time.sleep(0.25)
        ws_url = next(p["webSocketDebuggerUrl"] for p in pages if p["type"] == "page")
        c = CDP(await websockets.connect(ws_url, max_size=200 * 1024 * 1024))
        await c.call("Page.enable")
        await c.call("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1, mobile=False)
        await c.call("Page.navigate", url="http://localhost:8501")
        await c.js(WAIT_APP, wait=2)

        # 1. First visit: welcome / profile, search, tabs
        await c.shot("01_home")
        await c.js(f"({CLICK_BUTTON})('CONTINUE')")
        await c.js(WAIT_APP, wait=1)
        await c.shot("02_home_profile")

        # 2. Browse: ranked table + one restaurant's dish-by-dish details
        await c.js(f"({CLICK_BUTTON})('BROWSE ALL')")
        await c.js(f"({SCROLL_TO})('h4','ranked')", wait=1)
        await c.shot("03_browse_ranked")
        await c.js(f"({SCROLL_TO})('h3','')", wait=0.5)
        await c.js(f"({SCROLL_TO})('.gn-scores','')", wait=0.5)
        await c.js("window.scrollBy(0,-260)", wait=0.5)
        await c.shot("04_restaurant_card")

        # 3. Map
        await c.js(f"({CLICK_TAB})('MAP')", wait=4)
        await c.js(f"({SCROLL_TO})('[data-testid=stDeckGlJsonChart]','')", wait=2)
        await c.js("window.scrollBy(0,-90)", wait=1)
        await c.shot("05_map")

        # 4. Check a menu: the prompt-injection sample (saved result, no tokens)
        await c.js(f"({CLICK_TAB})('CHECK A MENU')")
        await c.js("""(async()=>{const i=[...document.querySelectorAll('input')].find(x=>x.getAttribute('aria-label')&&
            x.getAttribute('aria-label').startsWith('Or try a sample'));i.click();await new Promise(r=>setTimeout(r,700));
            const o=[...document.querySelectorAll('[role=option]')].find(x=>x.innerText==='injection_test');o&&o.click();
            await new Promise(r=>setTimeout(r,1200));return !!o})()""")
        await c.js(f"({CLICK_BUTTON})('CHECK THIS MENU')", wait=1)
        await c.js(f"({SCROLL_TO})('[data-testid=stAlert]','Blocked')", wait=0.8)
        await c.js("window.scrollBy(0,-90)", wait=0.5)
        await c.shot("06_injection_blocked")

        # 5. How it works: agent trace of that run, the team, costs, feedback
        await c.js(f"({CLICK_TAB})('HOW IT WORKS')")
        await c.js(f"({SCROLL_TO})('h3','How Go Nuts works')", wait=0.5)
        await c.shot("07_team")
        await c.js(f"({CLICK_BUTTON})('YOUR LAST REQUEST')", wait=2)
        await c.js(f"({SCROLL_TO})('h3','How Go Nuts works')", wait=0.5)
        await c.shot("08_agent_trace", full=True)
        await c.js(f"({CLICK_BUTTON})('COSTS')", wait=2)
        await c.js(f"({SCROLL_TO})('h3','How Go Nuts works')", wait=0.5)
        await c.shot("09_costs", full=True)

        # 6. Chef card (English, then Arabic)
        await c.js("window.scrollTo(0,0)", wait=0.5)
        await c.js(f"({CLICK_BUTTON})('CHEF CARD')", wait=2)
        await c.shot("10_chef_card_en")
        await c.js("""(async()=>{const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>x.innerText.trim()==='العربية');
            b&&b.click();await new Promise(r=>setTimeout(r,2000));return !!b})()""")
        await c.shot("11_chef_card_ar")

        # 7. Phone layout
        await c.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        await c.call("Page.navigate", url="http://localhost:8501")
        await c.js(WAIT_APP, wait=2)
        await c.shot("12_phone")
    finally:
        chrome.terminate()


asyncio.run(main())
