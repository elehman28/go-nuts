"""Record a captioned demo of Go Nuts (under 1 minute) with headless Chrome.

    python report/demo_video.py OUT_DIR      (app running on http://localhost:8501)

Writes OUT_DIR/frames/*.jpg, OUT_DIR/frames.ffconcat, narration clips (macOS `say`, made on this
computer) in OUT_DIR/voice and their start times in OUT_DIR/narration.json; encode with ffmpeg (see the end).
Uses saved results only (a restaurant already checked, the sample test menu), so it costs 0 tokens.
Captions are added to the page during recording only; the app itself is unchanged.
"""
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
FRAMES = OUT / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1280, 720
PORT = 9340
VOICE, RATE = "Allison (Enhanced)", 185  # the student's pick (free Enhanced voice from System Settings)
NARRATION = [
    "Go Nuts helps you eat out with a nut allergy. First, tell it what you're allergic to.",
    "Search any restaurant by name.",
    "You'll see its nut-risk score, and you can call the restaurant to ask, with one tap.",
    "Every dish is rated from the real menu, quoting the menu's own words.",
    "Or browse all eighty-nine checked restaurants, ranked for your allergies.",
    "The map shows three hundred eighty New Haven restaurants, colored by score.",
    "You can also check any menu. Paste it, link it, or snap a photo.",
    "Hidden instructions in a menu are blocked, and nut dishes are still flagged.",
    "And show staff an allergy chef card, in six languages.",
    "Go Nuts never calls food safe. Always tell your server, and carry epinephrine.",
]


def make_voice() -> list[float]:
    """One spoken clip per line; returns each clip's length in seconds."""
    (OUT / "voice").mkdir(exist_ok=True)
    lengths = []
    for i, line in enumerate(NARRATION):
        clip = OUT / "voice" / f"{i}.aiff"
        subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(clip), line], check=True)
        info = subprocess.run(["afinfo", str(clip)], capture_output=True, text=True).stdout
        lengths.append(float(info.split("estimated duration:")[1].split()[0]))
    return lengths


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


class Recorder:
    """Takes a JPEG of the page about 10 times a second on its own DevTools connection."""

    def __init__(self, cdp):
        self.cdp, self.frames, self.on = cdp, [], False

    async def run(self):
        self.on = True
        while self.on:
            t = time.monotonic()
            data = (await self.cdp.call("Page.captureScreenshot", format="jpeg", quality=82))["data"]
            self.frames.append((t, base64.b64decode(data)))
            await asyncio.sleep(max(0.0, 0.1 - (time.monotonic() - t)))

    def save(self):
        lines = ["ffconcat version 1.0"]
        for i, (t, img) in enumerate(self.frames):
            (FRAMES / f"{i:05}.jpg").write_bytes(img)
            nxt = self.frames[i + 1][0] if i + 1 < len(self.frames) else t + 0.1
            lines += [f"file 'frames/{i:05}.jpg'", f"duration {nxt - t:.3f}"]
        lines.append(f"file 'frames/{len(self.frames) - 1:05}.jpg'")
        (OUT / "frames.ffconcat").write_text("\n".join(lines) + "\n")
        return self.frames[-1][0] - self.frames[0][0]


SETUP = """(()=>{
  const st=document.createElement('style');st.textContent=`
  #demo-cap{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;max-width:900px;
    background:rgba(43,34,28,.92);color:#fffdf9;font:500 22px/1.35 'Libre Franklin',Arial,sans-serif;padding:12px 26px;
    border-radius:999px;box-shadow:0 6px 24px rgba(0,0,0,.18);transition:opacity .35s;text-align:center}
  #demo-cap b{color:#e8c39a;font-weight:600}
  .demo-ring{position:fixed;z-index:99998;border:3px solid #a8743f;border-radius:10px;pointer-events:none;
    animation:demoring .9s ease-out forwards}
  @keyframes demoring{0%{opacity:1;transform:scale(1.15)}100%{opacity:0;transform:scale(1)}}
  #demo-end{position:fixed;inset:0;z-index:100000;background:#fffdf9;display:flex;flex-direction:column;
    align-items:center;justify-content:center;font-family:'Old Standard TT',Georgia,serif;color:#3c2c20;opacity:0;transition:opacity .6s}
  #demo-end .b{font-size:84px} #demo-end .b i{color:#a8743f} #demo-end p{font:400 24px 'Libre Franklin',sans-serif;color:#5a4a3e;margin:10px}`;
  document.head.appendChild(st);
  const c=document.createElement('div');c.id='demo-cap';c.style.opacity=0;document.body.appendChild(c);return true})()"""
CAPTION = """((h)=>{const c=document.getElementById('demo-cap');c.style.opacity=0;
  setTimeout(()=>{c.innerHTML=h;c.style.opacity=h?1:0},250);return true})"""
# Find the element, scroll it into view, flash a ring around it, click it.
CLICK = """(async(sel,txt,click)=>{const els=[...document.querySelectorAll(sel)].filter(x=>x.getBoundingClientRect().width>5
  &&(!txt||x.innerText.trim().toUpperCase().startsWith(txt.toUpperCase())));const e=els[els.length-1];if(!e)return false;
  const r0=e.getBoundingClientRect();if(r0.top<60||r0.bottom>innerHeight-110){e.scrollIntoView({behavior:'smooth',block:'center'});
  await new Promise(r=>setTimeout(r,700));}
  const r=e.getBoundingClientRect(),g=document.createElement('div');g.className='demo-ring';
  Object.assign(g.style,{left:(r.left-6)+'px',top:(r.top-6)+'px',width:(r.width+12)+'px',height:(r.height+12)+'px'});
  document.body.appendChild(g);setTimeout(()=>g.remove(),1000);await new Promise(r=>setTimeout(r,450));
  if(click!==false)e.click();return true})"""
# Streamlit scrolls an inner container, not the window: find it, then scroll it.
BOX = """(()=>{const c=[...document.querySelectorAll('*')].find(e=>{const s=getComputedStyle(e);
  return (s.overflowY==='auto'||s.overflowY==='scroll')&&e.scrollHeight>e.clientHeight+50&&e.clientHeight>400});
  return c||document.scrollingElement})()"""
SCROLL = """(async(sel,txt,off)=>{const e=[...document.querySelectorAll(sel)].find(x=>x.offsetParent&&(!txt||x.innerText.includes(txt)));
  if(!e)return false;const c=""" + BOX + """;c.scrollTo({top:c.scrollTop+e.getBoundingClientRect().top-c.getBoundingClientRect().top-(off||90),
  behavior:'smooth'});await new Promise(r=>setTimeout(r,900));return true})"""
TOP = """(async()=>{document.querySelector('.gn-brand').scrollIntoView({behavior:'instant',block:'start'});
  await new Promise(r=>setTimeout(r,100));return true})()"""
IDLE = """(async()=>{for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,250));
  if(!document.querySelector('[data-testid=stStatusWidget]'))break;}return true})()"""
READY = """(async()=>{for(let i=0;i<180;i++){await new Promise(r=>setTimeout(r,500));
  if(document.querySelector('.gn-brand')&&!document.querySelector('[data-testid=stStatusWidget]'))return true;}return false})()"""


async def main():
    lengths = make_voice()
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
                               f"--user-data-dir={OUT / 'profile'}", "--hide-scrollbars", f"--window-size={W},{H}",
                               "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except OSError:
                time.sleep(0.25)
        url = next(p["webSocketDebuggerUrl"] for p in pages if p["type"] == "page")
        c = CDP(await websockets.connect(url, max_size=200 * 1024 * 1024))
        rec = Recorder(CDP(await websockets.connect(url, max_size=200 * 1024 * 1024)))
        await c.call("Page.enable")
        await c.call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
        await c.call("Page.navigate", url="http://localhost:8501")
        assert await c.js(READY), "app did not load"
        await c.js(SETUP, wait=1.5)

        spoken, voice_end = [], [0.0]

        async def speak(i):
            """Start narration line i once the previous line has finished."""
            while time.monotonic() < voice_end[0]:
                await asyncio.sleep(0.05)
            spoken.append((i, time.monotonic()))
            voice_end[0] = time.monotonic() + lengths[i] + 0.25

        async def cap(html, wait=0.0, line=None):
            if line is not None:
                await speak(line)
            await c.js(f"({CAPTION})({json.dumps(html)})", wait=wait)

        async def click(sel, txt="", wait=0.0, really=True):
            await c.js(f"({CLICK})({json.dumps(sel)},{json.dumps(txt)},{json.dumps(really)})")
            await c.js(IDLE, wait=wait)

        async def pick(aria, text):
            """Open a dropdown with a real mouse click, type to filter, press Enter."""
            box = await c.js(f"""(async()=>{{const i=document.querySelector('input[aria-label="{aria}"]');
                i.scrollIntoView({{behavior:'smooth',block:'center'}});await new Promise(r=>setTimeout(r,700));
                const r=i.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}})()""")
            for t in ("mousePressed", "mouseReleased"):
                await c.call("Input.dispatchMouseEvent", type=t, x=box[0], y=box[1], button="left", clickCount=1)
            await asyncio.sleep(0.5)
            for ch in text:
                await c.call("Input.insertText", text=ch)
                await asyncio.sleep(0.08)
            await asyncio.sleep(0.7)
            for t in ("keyDown", "keyUp"):
                await c.call("Input.dispatchKeyEvent", type=t, key="Enter", code="Enter", windowsVirtualKeyCode=13)
            await c.js(IDLE, wait=0.8)

        task = asyncio.create_task(rec.run())
        await asyncio.sleep(0.3)

        async def rclick(sel, txt):
            """A real mouse click on the element (Streamlit expanders ignore scripted clicks)."""
            box = await c.js(f"""(async()=>{{const e=[...document.querySelectorAll({json.dumps(sel)})].find(x=>x.offsetParent&&
                x.innerText.includes({json.dumps(txt)}));e.scrollIntoView({{behavior:'smooth',block:'center'}});
                await new Promise(r=>setTimeout(r,700));const r=e.getBoundingClientRect();return [r.left+40,r.top+r.height/2]}})()""")
            for t in ("mousePressed", "mouseReleased"):
                await c.call("Input.dispatchMouseEvent", type=t, x=box[0], y=box[1], button="left", clickCount=1)
            await c.js(IDLE, wait=0.6)

        def tab(name):
            return c.js(f"""(()=>{{const t=[...document.querySelectorAll('[role=tab]')].find(x=>
                x.innerText.toUpperCase().includes({json.dumps(name)}));t.click();return true}})()""")

        # Each step: caption first, then the action, then a short hold.
        # 1. Profile
        await cap("Tell Go Nuts <b>what you're allergic to</b>", 2.6, line=0)
        await click("button", "CONTINUE", 1.0)

        # 2. Search a restaurant: score and call button, then dish by dish
        await cap("Search any restaurant by name", line=1)
        await pick("Search", "September")
        await cap("See its <b>nut-risk score</b>, and <b>call to ask</b> in one tap", line=2)
        await c.js(f"({SCROLL})('h3','September in Bangkok',80)", wait=3.0)
        await cap("Every dish is rated, <b>quoting the menu's own words</b>", line=3)
        await rclick("summary", "Dish by dish")
        await c.js(f"({SCROLL})('summary','Dish by dish',60)", wait=3.4)

        # 3. Browse, ranked for the profile
        await cap("Browse <b>all 89 checked restaurants</b>, ranked for you", line=4)
        await rclick("summary", "Dish by dish")  # fold the long dish list away again
        await c.js(TOP, wait=0.6)
        await click("button", "BROWSE ALL", 0.4)
        await c.js(f"({SCROLL})('h4','ranked',80)", wait=3.0)

        # 4. Map
        await cap("See <b>380 restaurants</b> on the map, colored by score", line=5)
        await c.js(TOP, wait=0.5)
        await tab("MAP")
        await c.js(IDLE, wait=1.2)
        await c.js(f"({SCROLL})('[data-testid=stDeckGlJsonChart]','',70)", wait=3.0)

        # 5. Check a menu: hidden instructions blocked
        await cap("Or check <b>any menu</b>: paste it, link it or photograph it", line=6)
        await c.js(TOP, wait=0.5)
        await tab("CHECK A MENU")
        await c.js(IDLE, wait=0.6)
        await pick("Or try a sample menu (made up for testing)", "injection")
        await click("button", "CHECK THIS MENU", 0.3)
        await c.js("""(async()=>{for(let i=0;i<40;i++){await new Promise(r=>setTimeout(r,250));
            if([...document.querySelectorAll('[data-testid=stAlert]')].some(a=>a.innerText.includes('Blocked')))return true;}
            return false})()""")
        await cap("Hidden instructions in a menu get <b>blocked</b>", line=7)
        await c.js(f"({SCROLL})('[data-testid=stAlert]','Blocked',260)", wait=3.4)

        # 6. Chef card
        await cap("Show staff an <b>allergy chef card</b>, in six languages", line=8)
        await c.js(TOP, wait=0.6)
        await click("button", "CHEF CARD", 1.2)
        # The card opens in a dialog that covers the page, so the caption moves onto the dialog.
        await c.js("""(()=>{const d=document.querySelector('[role=dialog]'),c=document.getElementById('demo-cap');
            if(d&&c){d.prepend(c);Object.assign(c.style,{position:'relative',bottom:'auto',left:'auto',transform:'none',
            margin:'10px auto 4px',width:'fit-content'});}return !!d})()""", wait=0.4)
        await c.js("""(()=>{const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>x.innerText.trim()==='Español');
            b&&b.click();return !!b})()""")
        await c.js(IDLE, wait=2.2)

        box = await c.js("""(()=>{const b=[...document.querySelectorAll('[role=dialog] button')].find(x=>
            (x.getAttribute('aria-label')||'').toLowerCase().includes('close'));if(!b)return null;
            const r=b.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()""")
        if box:  # close the chef card dialog with a real click on its X
            for t in ("mousePressed", "mouseReleased"):
                await c.call("Input.dispatchMouseEvent", type=t, x=box[0], y=box[1], button="left", clickCount=1)
        await asyncio.sleep(0.5)

        # 7. End card (about 4 s)
        while time.monotonic() < voice_end[0]:
            await asyncio.sleep(0.05)
        await cap("")
        await c.js("""(()=>{const e=document.createElement('div');e.id='demo-end';e.innerHTML=
            "<div class='b'>go <i>nuts</i></div><p>Eat out with a nut allergy, without the guesswork.</p>"+
            "<p style='font-size:19px'>Go Nuts never calls food \\"safe\\". Always tell your server and carry epinephrine.</p>";
            document.body.appendChild(e);requestAnimationFrame(()=>e.style.opacity=1);return true})()""", wait=0.3)
        await speak(9)
        await asyncio.sleep(lengths[9] + 0.8)
        rec.on = False
        await task
        start = rec.frames[0][0]
        (OUT / "narration.json").write_text(json.dumps([{"clip": f"voice/{i}.aiff", "start": t - start} for i, t in spoken]))
        print(f"recorded {rec.save():.1f} s, {len(rec.frames)} frames, {len(spoken)} narration lines")
    finally:
        chrome.terminate()


asyncio.run(main())
# Encode: video from frames.ffconcat, plus each narration clip delayed to its start time, e.g.
#   ffmpeg -f concat -safe 0 -i frames.ffconcat -i voice/0.aiff ... -filter_complex "[1]adelay=300:all=1[a0];...;[a0][a1]...amix=inputs=10:normalize=0"
#          -map 0:v -map "[a]" -vf "fps=30,format=yuv420p" -c:v libx264 -crf 20 -c:a aac report/go-nuts-demo.mp4

