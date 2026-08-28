#!/usr/bin/env python3
"""Open one page in a throwaway profile and photograph the window.

  python3 utils/ui_shot.py chrome://settings settings.png
  python3 utils/ui_shot.py chrome://history history.png --size 1200x820

Passing a chrome:// URL on the command line does not work on its own: first
run replaces it with the new tab page. So the URL goes over DevTools once the
browser is up, which also gives us a load event to wait on instead of a guess.

The profile is fresh every time, so what gets photographed is what a new user
sees, shipped defaults included.
"""

import argparse
import base64
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import cdp
import config
import window_shot


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("out", type=Path)
    parser.add_argument("--out-dir", default="baseline", help="build under out/")
    parser.add_argument("--size", default="1100x780")
    parser.add_argument("--settle", type=float, default=2.5,
                        help="seconds after load, for fonts and async panels")
    parser.add_argument("--keep", action="store_true",
                        help="leave the browser running")
    parser.add_argument("--window", action="store_true",
                        help="capture the whole window instead of the page")
    args = parser.parse_args()

    binary = config.require_src() / "out" / args.out_dir / "chrome.exe"
    if not binary.is_file():
        raise SystemExit(f"no build at {binary}")

    port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="shiemi-shot-"))
    proc = subprocess.Popen([
        str(binary),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        f"--window-size={args.size.replace('x', ',')}",
        "--disable-field-trial-config",
        "--no-default-browser-check",
    ])

    try:
        target = cdp.wait_for_page(port, time.monotonic() + 40)
        if not target:
            raise SystemExit("devtools never came up")

        page = cdp.Target(target["webSocketDebuggerUrl"])
        page.call("Page.enable")
        page.call("Page.navigate", url=args.url)

        # Poll rather than wait on the event: chrome:// pages finish loading
        # before their web components have rendered anything.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if page.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.1)
        time.sleep(args.settle)

        if args.window:
            # PrintWindow asks the window to draw itself, which gets the
            # browser's own chrome but leaves composited page content blank.
            page.close()
            match = window_shot.best_window(pid=proc.pid)
            if not match:
                raise SystemExit("no visible window for the browser")
            hwnd, title, rect = match
            width, height, pixels = window_shot.capture(hwnd, rect)
            window_shot.write_png(args.out, width, height, pixels)
            print(f"{title}  {width}x{height} -> {args.out}")
        else:
            shot = page.call("Page.captureScreenshot", format="png")
            args.out.write_bytes(base64.b64decode(shot["data"]))
            page.close()
            print(f"{args.url} -> {args.out}")
    finally:
        if not args.keep:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
