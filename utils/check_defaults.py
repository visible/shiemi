#!/usr/bin/env python3
"""Prove every shipped default actually reaches a new profile.

  python3 utils/check_defaults.py
  python3 utils/check_defaults.py --as-installed --binary <installed exe>

A misspelled pref path in defaults/initial_preferences is silent: the file
still parses, the browser still starts, and the setting simply never applies.
Nothing catches that by eye, because the wrong name looks exactly like the
right one. So every key in the file is read back out of the profile Chromium
built from it, and a key that did not arrive fails the run.

Opens a real window, and there is no headless option: --headless=new skips
first-run processing, so the file is never read and every key comes back
missing. Nothing else here needs a window.

Also does not pass --no-first-run, for the same reason.

--as-installed reads the file the installer put beside the browser instead of
copying ours in. Use it on a real install: staging a file into the installer
archive does not mean setup ever places it, and the difference is invisible
from the build tree.

Exit code is 1 if any key is missing or arrived with a different value.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import config

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"
DEFAULTS_FILE = config.ROOT / "defaults" / "initial_preferences"


def flatten(node, prefix: str = "") -> dict:
    """Nested prefs to dotted paths, stopping at lists and scalars."""
    flat = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, path))
        else:
            flat[path] = value
    return flat


def lookup(prefs: dict, path: str):
    """Value at a dotted path, or KeyError if any segment is absent."""
    node = prefs
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def seed_and_launch(binary: Path, wait: int, seed: bool = True) -> dict:
    """Run once against a fresh profile and return the prefs it wrote."""
    shipped = binary.parent / "initial_preferences"
    if seed:
        shutil.copyfile(DEFAULTS_FILE, shipped)
    elif not shipped.exists():
        raise SystemExit(
            f"no initial_preferences beside {binary}\n"
            "The installer did not place it, so this browser ships with"
            " Chromium's defaults and none of ours.")
    elif shipped.read_bytes() != DEFAULTS_FILE.read_bytes():
        raise SystemExit(f"{shipped} differs from {DEFAULTS_FILE}")

    profile = Path(tempfile.mkdtemp(prefix="shiemi-defaults-"))
    proc = subprocess.Popen([
        str(binary),
        f"--user-data-dir={profile}",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        "about:blank",
    ])
    try:
        time.sleep(wait)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)

    written = profile / "Default" / "Preferences"
    try:
        prefs = json.loads(written.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not read {written}: {exc}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return prefs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--wait", type=int, default=25,
                        help="seconds before reading the prefs back")
    parser.add_argument("--as-installed", action="store_true",
                        help="trust the file already beside the binary rather"
                             " than copying ours in, to test a real install")
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")

    wanted = flatten(json.loads(DEFAULTS_FILE.read_text(encoding="utf-8")))
    print(f"binary   {args.binary}")
    print(f"checking {len(wanted)} shipped default(s)\n")

    prefs = seed_and_launch(args.binary, args.wait, seed=not args.as_installed)

    problems = []
    for path, expected in sorted(wanted.items()):
        try:
            actual = lookup(prefs, path)
        except KeyError:
            problems.append(f"{path}: never reached the profile")
            print(f"  MISSING  {path} = {expected!r}")
            continue
        if actual == expected:
            print(f"  ok       {path} = {expected!r}")
        else:
            problems.append(f"{path}: wanted {expected!r}, got {actual!r}")
            print(f"  WRONG    {path} = {actual!r}, wanted {expected!r}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        print("\nA pref that does not arrive is usually a path that does not"
              " exist. Check the registration in the Chromium tree rather than"
              " the spelling alone.")
        return 1

    print(f"\nall {len(wanted)} default(s) landed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
