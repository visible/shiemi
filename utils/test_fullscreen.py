#!/usr/bin/env python3
"""Prove contained fullscreen keeps a page's fullscreen inside the window.

  python3 utils/test_fullscreen.py
  python3 utils/test_fullscreen.py --headless

Runs the same page twice, once with shiemi.contained_fullscreen off and once
with it on, and compares what requestFullscreen() did to the window.

Both runs have to reach fullscreen, or the comparison proves nothing: the
difference being measured is whether the window grew to the display, not
whether the page went fullscreen at all. outerHeight is the measure rather
than a window state flag, since it is what the user actually sees.

innerHeight is the second measure, and the two together are what separate this
from a page merely filling the content area: contained fullscreen collapses the
tab strip and the toolbar, so the viewport grows by their height while the
window itself does not move.

The page is served over HTTP because the Fullscreen API is gated on a real
origin, and about:blank and data: URLs are both opaque.

Exit code is 1 if either run misbehaved.
"""

import argparse
import http.server
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import cdp
import config
import window_shot

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"
PREF = "shiemi.contained_fullscreen"
WINDOW_HEIGHT = 600

PAGE = b"""<!doctype html><title>fullscreen</title>
<div id="box" style="width:80px;height:60px;background:#c60"></div>
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve() -> tuple:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def write_pref(profile: Path, value: bool) -> None:
    """Seed the profile's own Preferences, which first run does not overwrite."""
    default = profile / "Default"
    default.mkdir(parents=True, exist_ok=True)
    section, key = PREF.split(".")
    (default / "Preferences").write_text(
        json.dumps({section: {key: value}}), encoding="utf-8")


def measure(page) -> dict:
    return page.evaluate(
        "({inner: window.innerHeight, outer: window.outerHeight,"
        " screen: window.screen.height,"
        " fullscreenElement: document.fullscreenElement ?"
        " document.fullscreenElement.id : null})"
    )


def shoot(pid: int, out: Path) -> None:
    match = window_shot.best_window(pid=pid)
    if not match:
        print(f"    no window to capture for pid {pid}")
        return
    hwnd, _, rect = match
    width, height, pixels = window_shot.capture(hwnd, rect)
    window_shot.write_png(out, width, height, pixels)
    print(f"    shot               {width}x{height} -> {out}")


def probe(binary: Path, http_port: int, contained: bool, headless: bool,
          shot: Path | None = None) -> dict:
    devtools_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="shiemi-fs-"))
    write_pref(profile, contained)

    proc = subprocess.Popen([
        str(binary),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={devtools_port}",
        f"--window-size=900,{WINDOW_HEIGHT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-field-trial-config",
        # A window that never comes to the front is treated as occluded and
        # stops painting, which captures as a black rectangle.
        "--disable-features=CalculateNativeWinOcclusion",
        *(["--headless"] if headless else []),
        f"http://127.0.0.1:{http_port}/",
    ])

    try:
        target = cdp.wait_for_page(devtools_port, time.monotonic() + 60)
        if not target:
            raise SystemExit("devtools never served a page target")
        page = cdp.Target(target["webSocketDebuggerUrl"])

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if page.evaluate("!!document.getElementById('box')"):
                break
            time.sleep(0.05)

        before = measure(page)

        # requestFullscreen is gated on a user gesture, which CDP can forge.
        page.call(
            "Runtime.evaluate",
            expression="document.getElementById('box').requestFullscreen()"
                       ".then(() => 'ok', e => e.name)",
            awaitPromise=True,
            returnByValue=True,
            userGesture=True,
        )

        # The window transition is asynchronous even once the promise settles.
        deadline = time.monotonic() + 10
        after = measure(page)
        while time.monotonic() < deadline:
            after = measure(page)
            if after["fullscreenElement"] and after["outer"] != before["outer"]:
                break
            time.sleep(0.1)

        if shot and not headless:
            shoot(proc.pid, shot)

        # Exiting matters as much as entering: a window left with no tab strip
        # and no toolbar is indistinguishable from a broken one.
        page.call(
            "Runtime.evaluate",
            expression="document.exitFullscreen().then(() => 'ok', e => e.name)",
            awaitPromise=True,
            returnByValue=True,
            userGesture=True,
        )

        deadline = time.monotonic() + 10
        restored = measure(page)
        while time.monotonic() < deadline:
            restored = measure(page)
            if not restored["fullscreenElement"] and \
                    restored["inner"] == before["inner"]:
                break
            time.sleep(0.1)

        page.close()
        return {"before": before, "after": after, "restored": restored}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--headless", action="store_true",
                        help="run without opening a window")
    parser.add_argument("--shot", type=Path,
                        help="capture the window while it is in fullscreen")
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")

    server, http_port = serve()
    failures = []
    try:
        for contained in (False, True):
            name = "on " if contained else "off"
            shot = None
            if args.shot:
                shot = args.shot.with_stem(
                    f"{args.shot.stem}-{'on' if contained else 'off'}")
            result = probe(args.binary, http_port, contained, args.headless,
                           shot)
            before, after = result["before"], result["after"]
            restored = result["restored"]
            took_over = after["outer"] >= after["screen"]

            print(f"  {PREF} {name}")
            print(f"    fullscreenElement  {after['fullscreenElement']}")
            print(f"    outerHeight        {before['outer']} -> {after['outer']}"
                  f"  (display {after['screen']})")
            gained = after["inner"] - before["inner"]
            print(f"    innerHeight        {before['inner']} -> {after['inner']}"
                  f"  ({gained:+d})")
            print(f"    on exit            {restored['inner']}"
                  f"  (was {before['inner']})")

            if restored["inner"] != before["inner"]:
                failures.append(
                    f"pref {name}: the chrome did not come back on exit"
                    f" ({before['inner']} -> {restored['inner']})")
            elif after["fullscreenElement"] != "box":
                failures.append(f"pref {name}: the page never entered fullscreen")
            elif contained and took_over:
                failures.append("pref on: the window still took over the display")
            elif contained and gained <= 0:
                failures.append("pref on: the viewport did not grow, so the tab"
                                " strip and toolbar are still taking their space")
            elif not contained and not took_over:
                failures.append("pref off: the window did not take over the display,"
                                " so the two runs are indistinguishable")
    finally:
        server.shutdown()

    if failures:
        print("\nFAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("\ncontained fullscreen holds the page inside the window and"
          " collapses the chrome; off, the window still goes to the display")
    return 0


if __name__ == "__main__":
    sys.exit(main())
