#!/usr/bin/env python3
"""Prove a Manifest V2 content blocker can still block a request.

  python3 utils/test_mv2.py
  python3 utils/test_mv2.py --keep-open

Manifest V3 removes blocking webRequest, which is the capability every content
blocker is built on. Re-enabling V2 is only worth anything if a request that an
extension cancels never reaches the network, so this serves two endpoints from
a local server, asks the page to fetch both, and checks that the one the
extension cancels never arrives.

The local server is the point: a blocked request that still shows up in the
server log was not blocked, however the page reports it.

Exit code is 1 if the extension failed to load or the request got through.
"""

import argparse
import http.server
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import cdp
import config

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"
EXTENSION = Path(__file__).resolve().parent.parent / "tests" / "mv2-extension"

PAGE = b"<!doctype html><title>mv2</title>"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(received: list) -> tuple:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.path)
            body = PAGE if self.path == "/page" else b"ok"
            self.send_response(200)
            self.send_header("Content-Type",
                             "text/html" if self.path == "/page" else "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def fetch_status(page, url: str) -> str:
    """"ok" if the fetch completed, else "blocked"."""
    return page.evaluate(
        f"fetch({url!r}, {{cache: 'no-store'}})"
        ".then(r => 'ok').catch(e => 'blocked')"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--keep-open", action="store_true",
                        help="leave the browser running to inspect by hand")
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")
    if not (EXTENSION / "manifest.json").exists():
        raise SystemExit(f"no extension at {EXTENSION}")

    received = []
    server, http_port = serve(received)
    devtools_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="shiemi-mv2-"))

    proc = subprocess.Popen([
        str(args.binary),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={devtools_port}",
        f"--load-extension={EXTENSION}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ])

    failures = []
    try:
        target = cdp.wait_for_page(devtools_port, time.monotonic() + 60)
        if not target:
            raise SystemExit("devtools never served a page target")

        page = cdp.Target(target["webSocketDebuggerUrl"])
        page.call("Page.enable")

        # A persistent background page registers its listener during startup,
        # and the fetches below would race it.
        time.sleep(3)

        extensions = [t for t in cdp.targets(devtools_port)
                      if t.get("url", "").startswith("chrome-extension://")]
        if extensions:
            print(f"  extension loaded  {extensions[0]['title']}")
        else:
            failures.append("extension did not load, so nothing was tested")

        page.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/page")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if page.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.05)

        allowed = fetch_status(page, f"http://127.0.0.1:{http_port}/allowed")
        blocked = fetch_status(page, f"http://127.0.0.1:{http_port}/blocked")

        print(f"  control request   {allowed}")
        print(f"  blocked request   {blocked}")

        if allowed != "ok":
            failures.append("the control request failed, so the test proves nothing")
        if blocked != "blocked":
            failures.append("the extension did not cancel the request")
        if "/blocked" in received:
            failures.append("the cancelled request still reached the server")
        if "/allowed" not in received:
            failures.append("the control request never reached the server")

        page.close()
    finally:
        if args.keep_open:
            print(f"\nbrowser left running on devtools port {devtools_port}")
        else:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
        server.shutdown()

    print(f"  server saw        {', '.join(received) or 'nothing'}")

    if failures:
        print("\nFAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("\nblocking webRequest works: the cancelled request never left the browser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
