#!/usr/bin/env python3
"""Launch a build for hand testing, with prefs set and verified.

  python3 utils/launch.py --pref shiemi.contained_fullscreen=true
  python3 utils/launch.py --url https://www.youtube.com/ --keep-profile

Setting a pref by hand before launch is easy to get wrong in a way that looks
like a broken feature rather than a bad command: a --user-data-dir containing a
space gets split by the shell, Chromium starts on a different directory without
complaining, and the seeded pref is never read. A spaced path is refused here
for that reason, and the prefs are read back afterwards so a seed that failed
to land shows up before the browser is handed over.

The read-back proves the pref reached the directory Chromium was pointed at. It
does not prove Chromium parsed it, since prefs are committed lazily and the file
may still be the seed - only using the feature proves that.

The browser is left running.
"""

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import cdp
import config


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def parse(assignments: list[str]) -> dict:
    prefs = {}
    for assignment in assignments:
        key, _, raw = assignment.partition("=")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        target = prefs
        *parents, leaf = key.split(".")
        for parent in parents:
            target = target.setdefault(parent, {})
        target[leaf] = value
    return prefs


def read_back(profile: Path, keys: list[str]) -> dict:
    """Read the prefs back out of the directory the browser was pointed at."""
    path = profile / "Default" / "Preferences"
    try:
        live = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    found = {}
    for key in keys:
        node = live
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        found[key] = node
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pref", action="append", default=[],
                        metavar="KEY=JSON", help="a profile pref to set")
    parser.add_argument("--url", default="about:blank")
    parser.add_argument("--out-dir", default="baseline")
    parser.add_argument("--size", default="1280,800")
    parser.add_argument("--profile", default=None,
                        help="profile directory; must not contain a space")
    parser.add_argument("--keep-profile", action="store_true",
                        help="reuse an existing profile instead of resetting it")
    args = parser.parse_args()

    binary = config.require_src() / "out" / args.out_dir / "chrome.exe"
    if not binary.is_file():
        raise SystemExit(f"no build at {binary}")

    profile = Path(args.profile) if args.profile else config.ROOT / ".profile"
    if " " in str(profile):
        raise SystemExit(f"profile path contains a space, which the shell will "
                         f"split and Chromium will silently ignore: {profile}")

    if not args.keep_profile:
        shutil.rmtree(profile, ignore_errors=True)

    prefs = parse(args.pref)
    if prefs:
        default = profile / "Default"
        default.mkdir(parents=True, exist_ok=True)
        target = default / "Preferences"
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            existing.update(prefs)
            prefs = existing
        target.write_text(json.dumps(prefs), encoding="utf-8")

    port = free_port()
    proc = subprocess.Popen([
        str(binary),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        f"--window-size={args.size}",
        "--no-first-run",
        "--no-default-browser-check",
        args.url,
    ])

    if not cdp.wait_for_page(port, time.monotonic() + 60):
        raise SystemExit("devtools never came up, so the browser is not healthy")

    print(f"pid      {proc.pid}")
    print(f"profile  {profile}")
    print(f"url      {args.url}")

    keys = [a.partition("=")[0] for a in args.pref]
    if keys:
        # Chromium rewrites Preferences during startup, so what is in the file
        # now is its own view of the pref rather than the seed.
        time.sleep(3)
        live = read_back(profile, keys)
        for key in keys:
            state = live.get(key)
            mark = "ok " if state is not None else "MISSING"
            print(f"{mark:8} {key} = {state}")
        if any(live.get(key) is None for key in keys):
            print("\nA missing pref means the browser is not running what you "
                  "asked for.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
