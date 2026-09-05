#!/usr/bin/env python3
"""Prove the shipped search default holds in every region, not just ours.

  python3 utils/check_search_default.py

The default engine comes from a per-region list, so a build tested in one
country says nothing about the rest. A region whose list omits our engine
silently falls back to that region's own first entry, which is usually the
one we are trying not to ship.

Launches a fresh profile per region with --search-engine-choice-country and
asks the settings page which engine is marked default. Reading the profile's
Preferences file instead does not work: an untouched prepopulated default is
never written there, so every region looks empty whatever the answer.

Exit code is 1 if any region did not land on the wanted engine.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cdp
import config

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "release" / "chrome.exe"

# Deliberately a mix: EEA members, the anglosphere outside it, and large
# non-EEA markets, since only the EEA lists are required to be broad.
REGIONS = ("GB", "US", "DE", "FR", "JP", "BR", "IN", "AU", "CA", "ZA")

WANTED = "duckduckgo.com"


# cr.ts puts only webUIResponse on the window, not sendWithPromise, so the
# reply has to be intercepted by hand.
ASK = """
new Promise((resolve, reject) => {
  const id = 'shiemiSearchDefault';
  const prev = window.cr.webUIResponse;
  window.cr.webUIResponse = (cbid, ok, payload) => {
    try { prev(cbid, ok, payload); } catch (e) {}
    if (cbid === id) {
      const list = (payload && payload.defaults) || [];
      resolve(list.find(e => e.default) || {keyword: '?', name: '?'});
    }
  };
  chrome.send('getSearchEnginesList', [id]);
  setTimeout(() => reject(new Error('no reply from the settings handler')),
             10000);
})
"""

READY = "!!(window.cr && window.cr.webUIResponse && window.chrome &&" \
        " window.chrome.send)"


def default_engine(binary: Path, country: str, wait: int, port: int) -> tuple:
    """The keyword and name of the engine a fresh profile settles on."""
    profile = Path(tempfile.mkdtemp(prefix="shiemi-search-"))
    proc = subprocess.Popen([
        str(binary),
        f"--user-data-dir={profile}",
        f"--search-engine-choice-country={country}",
        f"--remote-debugging-port={port}",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        "--disable-features=CalculateNativeWinOcclusion",
        "about:blank",
    ])
    try:
        info = cdp.wait_for_page(port, time.monotonic() + wait)
        page = cdp.Target(info["webSocketDebuggerUrl"])
        # First run replaces any URL given on the command line, so the page
        # has to be sent there afterwards.
        page.call("Page.navigate", url="chrome://settings/search")
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                if page.evaluate(READY):
                    break
            except RuntimeError:
                pass
            time.sleep(0.25)
        else:
            raise SystemExit(f"{country}: settings page never came up")
        engine = page.evaluate(ASK) or {}
        page.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)

    return engine.get("keyword", "?"), engine.get("name", "?")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--wait", type=int, default=25,
                        help="seconds to let the settings page come up")
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument("--regions", nargs="*", default=list(REGIONS))
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")

    print(f"binary  {args.binary}")
    print(f"wanted  {WANTED}\n")

    wrong = []
    for country in args.regions:
        keyword, name = default_engine(
            args.binary, country, args.wait, args.port)
        if keyword == WANTED:
            print(f"  ok     {country}  {name} ({keyword})")
        else:
            wrong.append(f"{country}: {name} ({keyword})")
            print(f"  WRONG  {country}  {name} ({keyword})")

    if wrong:
        print(f"\n{len(wrong)} region(s) did not get {WANTED}:")
        for item in wrong:
            print(f"  {item}")
        print("\nThose regions' prepopulated lists do not contain it, so the"
              " fallback picked their first entry instead.")
        return 1

    print(f"\nall {len(args.regions)} region(s) default to {WANTED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
