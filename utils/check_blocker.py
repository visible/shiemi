#!/usr/bin/env python3
"""Prove the bundled blocker installs itself and blocks, on a fresh profile.

  python3 utils/check_blocker.py
  python3 utils/check_blocker.py --binary "%LOCALAPPDATA%/Shiemi/Application/chrome.exe"

The browser ships a content blocker, so three things have to be true and none
of them are true by construction:

  it arrives     without --load-extension, from the Extensions directory the
                 installer lays down, enabled rather than waiting behind a
                 prompt
  it blocks      a request to a host on its filter lists never leaves the
                 browser
  it is removable  a blocker the user cannot turn off is adware, however
                 well meant

The block is read off the network stack rather than the page, because the page
cannot tell being blocked from being offline. A blocker has two ways to stop a
request and uses both: cancelling it, which shows up as ERR_BLOCKED_BY_CLIENT,
or redirecting it to a neutered stub inside the extension, which is what most
ad script rules do so the site does not break. Either counts. What must never
appear is a response from the ad host itself, and a control request served
locally must come back untouched.

Exit code is 1 if any of the three fails.
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
import fetch_ublock

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"

# Long-standing entries on the default lists. Two rather than one so a single
# rule changing upstream does not decide the answer. Both are stopped before
# DNS, so this needs no network and contacts nobody.
ADS = (
    "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js",
    "https://static.doubleclick.net/instream/ad_status.js",
)

BLOCKED_ERROR = "ERR_BLOCKED_BY_CLIENT"
STUB = f"chrome-extension://{fetch_ublock.EXTENSION_ID}/"

PAGE = ("<!doctype html><title>blocker</title>\n"
        + "".join(f'<script src="{url}"></script>\n' for url in ADS)
        + '<script src="/control.js"></script>\n')

# developerPrivate is only reachable from a WebUI page, which is why this runs
# against chrome://extensions rather than the test page.
LIST_EXTENSIONS = """
new Promise(resolve => chrome.developerPrivate.getExtensionsInfo(
  {includeDisabled: true, includeTerminated: true},
  list => resolve(JSON.stringify(list.map(e => ({
    id: e.id,
    name: e.name,
    version: e.version,
    state: e.state,
    location: e.location,
    mustRemainInstalled: e.mustRemainInstalled,
  }))))))
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def verdict(page, url: str) -> str:
    """How a request for url ended: blocked, stubbed, or the response it got.

    A request keeps its id across redirects, so following the id is what tells
    a stub apart from the ad host answering.
    """
    ids = {r["requestId"] for r in page.seen("Network.requestWillBeSent")
           if r.get("request", {}).get("url") == url}
    if not ids:
        return "never requested"

    for failure in page.seen("Network.loadingFailed"):
        if failure["requestId"] in ids and BLOCKED_ERROR in failure.get(
                "errorText", ""):
            return "cancelled"

    for sent in page.seen("Network.requestWillBeSent"):
        if (sent["requestId"] in ids
                and sent.get("request", {}).get("url", "").startswith(STUB)):
            return "stubbed"

    for received in page.seen("Network.responseReceived"):
        if received["requestId"] in ids:
            response = received.get("response", {})
            return f"answered {response.get('status')} by {response.get('url', '')[:60]}"

    return "no outcome recorded"


def serve() -> tuple:
    body = PAGE.encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            payload = body if self.path == "/page" else b"void 0;\n"
            kind = "text/html" if self.path == "/page" else "text/javascript"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def wait_for_blocker(port: int, deadline: float) -> dict:
    """The blocker's entry once it has installed itself, else an empty dict."""
    while time.monotonic() < deadline:
        for target in cdp.targets(port):
            url = target.get("url", "")
            if url.startswith(f"chrome-extension://{fetch_ublock.EXTENSION_ID}/"):
                return target
        time.sleep(0.5)
    return {}


def describe(page) -> dict:
    """The blocker as the extensions page sees it."""
    page.call("Page.navigate", url="chrome://extensions")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if page.evaluate("!!(window.chrome && chrome.developerPrivate)"):
                break
        except RuntimeError:
            pass
        time.sleep(0.25)
    else:
        raise SystemExit("the extensions page never came up")

    listed = json.loads(page.evaluate(LIST_EXTENSIONS) or "[]")
    for entry in listed:
        if entry["id"] == fetch_ublock.EXTENSION_ID:
            return entry
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--wait", type=int, default=90,
                        help="seconds to allow for the blocker to compile its"
                             " filter lists on a new profile")
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")

    staged = args.binary.parent / "Extensions" / fetch_ublock.CRX_NAME
    if not staged.exists():
        raise SystemExit(
            f"no blocker beside the browser: {staged} is missing.\n"
            "Nothing would install it, so this build ships without one.")

    server, http_port = serve()
    devtools_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="shiemi-blocker-"))
    failures = []

    proc = subprocess.Popen([
        str(args.binary),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={devtools_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=CalculateNativeWinOcclusion",
        "about:blank",
    ])

    try:
        target = cdp.wait_for_page(devtools_port, time.monotonic() + 60)
        if not target:
            raise SystemExit("devtools never served a page target")

        deadline = time.monotonic() + args.wait
        if wait_for_blocker(devtools_port, deadline):
            print(f"  installed itself  uBlock Origin {fetch_ublock.VERSION}")
        else:
            failures.append(
                "the blocker never appeared, so nothing below was tested")

        entry = describe(cdp.Target(target["webSocketDebuggerUrl"]))
        removable = "removable" if not entry.get("mustRemainInstalled") else "locked in"
        print(f"  extensions page   {entry.get('state', 'absent')}, {removable}")
        if entry.get("state") != "ENABLED":
            failures.append(
                f"it is {entry.get('state', 'absent')}, not enabled, so the"
                " user has to go and switch on their own blocker")
        if entry.get("mustRemainInstalled"):
            failures.append("it cannot be uninstalled, which makes it adware")

        # A new profile compiles the filter lists before anything is blocked,
        # and there is no event for having finished, so the page is retried.
        page = cdp.Target(target["webSocketDebuggerUrl"])
        page.call("Network.enable")
        verdicts = {}
        while True:
            page.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/page")
            page.drain(5)
            verdicts = {url: verdict(page, url) for url in ADS}
            if all(v in ("cancelled", "stubbed") for v in verdicts.values()):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(1)

        for url, outcome in verdicts.items():
            print(f"  {url.split('/')[2]:<32} {outcome}")
        control = verdict(page, f"http://127.0.0.1:{http_port}/control.js")
        print(f"  control request                  {control}")

        for url, outcome in verdicts.items():
            if outcome not in ("cancelled", "stubbed"):
                failures.append(f"{url} was not blocked: {outcome}")
        if not control.startswith("answered 200"):
            failures.append(
                f"the control request came back '{control}', so this proves"
                " nothing about filtering")

        page.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.shutdown()

    if failures:
        print("\nFAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("\nthe bundled blocker installs itself, blocks, and can be removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
