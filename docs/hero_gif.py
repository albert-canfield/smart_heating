"""Record the animated README cover (docs/hero-anim.html) as docs/images/hero.gif.

    .venv/bin/python docs/hero_gif.py            # record and encode
    .venv/bin/python docs/hero_gif.py --frames 0 4500 9000   # just these moments, as PNGs (to check framing)

One headless Chrome, driven over the DevTools protocol: setFrame(t) for every frame, a screenshot each,
then ffmpeg (one palette for the whole loop, only changed areas per frame) and gifsicle to shrink it.
"""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import aiohttp

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DOCS = Path(__file__).resolve().parent
PAGE = DOCS / "hero-anim.html"
OUT = DOCS / "images" / "hero.gif"
W, H, FPS = 1200, 570, 12


class Tab:
    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws, self.n, self.errors = ws, 0, []

    async def send(self, method: str, **params):
        self.n += 1
        await self.ws.send_json({"id": self.n, "method": method, "params": params})
        while True:
            msg = json.loads((await self.ws.receive()).data)
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(msg["params"]["exceptionDetails"])
            elif msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] in ("error", "warning"):
                self.errors.append(msg["params"]["args"])
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expr: str):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"{expr}: {r['exceptionDetails'].get('exception', {}).get('description')}")
        return r["result"].get("value")


async def record(frames: list[int], out_dir: Path) -> list[Path]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        chrome = subprocess.Popen([CHROME, "--headless=new", "--hide-scrollbars", "--remote-debugging-port=0",
                                   f"--user-data-dir={profile}", "--force-device-scale-factor=1", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port_file = Path(profile) / "DevToolsActivePort"
            for _ in range(100):
                if port_file.exists() and port_file.read_text().strip():
                    break
                await asyncio.sleep(0.1)
            port = port_file.read_text().split()[0]
            async with aiohttp.ClientSession() as http:
                pages = await (await http.get(f"http://127.0.0.1:{port}/json/list")).json()
                url = next(p["webSocketDebuggerUrl"] for p in pages if p["type"] == "page")
                async with http.ws_connect(url, max_msg_size=0) as ws:
                    tab = Tab(ws)
                    await tab.send("Runtime.enable")
                    await tab.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
                    await tab.send("Page.navigate", url=PAGE.as_uri())
                    for _ in range(200):
                        if await tab.js("document.readyState") == "complete" and await tab.js("typeof window.heroReady") == "object":
                            break
                        await asyncio.sleep(0.05)
                    await tab.js("window.heroReady")
                    paths = []
                    for i, t in enumerate(frames):
                        await tab.js(f"window.setFrame({t})")
                        shot = await tab.send("Page.captureScreenshot", format="png")
                        p = out_dir / f"f{i:04d}.png"
                        p.write_bytes(base64.b64decode(shot["data"]))
                        paths.append(p)
                    if tab.errors:
                        print("page errors:", json.dumps(tab.errors, indent=1)[:2000])
                    return paths
        finally:
            chrome.terminate()
            chrome.wait(timeout=10)


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--frames"]:
        out = Path(tempfile.mkdtemp())
        for p in asyncio.run(record([int(a) for a in args[1:]], out)):
            print(p)
        return
    end = 20500
    frames = list(range(0, end, round(1000 / FPS)))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asyncio.run(record(frames, tmp))
        raw = tmp / "raw.gif"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"),
                        "-vf", "split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];"
                               "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                        "-loop", "0", str(raw)], check=True)
        if shutil.which("gifsicle"):
            subprocess.run(["gifsicle", "-O3", "--lossy=60", str(raw), "-o", str(OUT)], check=True)
        else:
            shutil.copy(raw, OUT)
    print(f"{OUT.relative_to(DOCS.parent)}: {len(frames)} frames, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
