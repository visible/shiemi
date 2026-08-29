#!/usr/bin/env python3
"""Report what the component updater fetches onto a cold profile.

  python3 utils/audit_components.py
  python3 utils/audit_components.py --baseline
  python3 utils/audit_components.py --field-trial-config

The network audit answers which hosts are contacted. This answers the other
half: what arrives, and how big it is. Payloads are far easier to attribute
than requests, because each component installs into a directory named after
itself, so a single listing says exactly which subsystem reached out.

Deliberately does not pass --disable-field-trial-config. Upstream's testing
config is compiled in and applied by default in an unbranded build, so a run
that switched it off would measure a browser nobody ships. Pass
--field-trial-config to switch it off anyway and compare.

The first update check is one minute after startup, so --component-updater=
fast-update is used to bring it down to ten seconds. Downloads still take as
long as they take, hence the wait.

Exit code is 1 under --baseline if a component outside tests/components-
allowed.txt installed anything.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import config

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"
ALLOWED_FILE = config.ROOT / "tests" / "components-allowed.txt"

# Written by the browser itself rather than the component updater, so they are
# not components and never appear in the report.
NOT_COMPONENTS = {
    "Default", "Crashpad", "GPUPersistentCache", "ShaderCache",
    "GrShaderCache", "GraphiteDawnCache", "segmentation_platform",
    "component_crx_cache", "extensions_crx_cache", "Safe Browsing",
    "Subresource Filter", "OptimizationHints", "Local Traces",
    "BrowserMetrics",
}


def read_allowed() -> dict:
    """Component directory name -> the reason it is allowed to download."""
    allowed = {}
    if not ALLOWED_FILE.exists():
        return allowed
    for raw in ALLOWED_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, reason = line.partition("|")
        allowed[name.strip()] = reason.strip()
    return allowed


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            # A file the browser is still writing can vanish mid-walk.
            pass
    return total


def survey(profile: Path) -> dict:
    """Every top-level directory that holds bytes, with its size."""
    found = {}
    for item in sorted(profile.iterdir()):
        if not item.is_dir() or item.name in NOT_COMPONENTS:
            continue
        size = directory_size(item)
        if size:
            found[item.name] = size
    return found


def run(binary: Path, wait: int, headless: bool,
        field_trial_config: bool) -> dict:
    profile = Path(tempfile.mkdtemp(prefix="shiemi-components-"))
    command = [
        str(binary),
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--component-updater=fast-update",
    ]
    if field_trial_config:
        command.append("--disable-field-trial-config")
    if headless:
        command.append("--headless=new")
    command.append("about:blank")

    proc = subprocess.Popen(command)
    try:
        # Reported as it goes, because the interesting failure is a download
        # that is still growing when the clock runs out.
        deadline = time.monotonic() + wait
        previous = 0
        while time.monotonic() < deadline:
            time.sleep(5)
            total = sum(survey(profile).values())
            if total != previous:
                print(f"    {int(total / 1024 / 1024):5d} MB so far")
                previous = total
        return survey(profile)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        # Held on Windows until the child processes are gone.
        time.sleep(2)
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--wait", type=int, default=180,
                        help="seconds to let downloads run")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="draw offscreen, so nothing steals focus")
    parser.add_argument("--window", dest="headless", action="store_false",
                        help="show the window instead")
    parser.add_argument("--field-trial-config", action="store_true",
                        help="switch off upstream's compiled-in testing config")
    parser.add_argument("--baseline", action="store_true",
                        help="fail if anything outside the allow list arrived")
    args = parser.parse_args()

    if not args.binary.exists():
        raise SystemExit(f"no browser at {args.binary} - build it first")

    print(f"binary  {args.binary}")
    print(f"waiting {args.wait}s with the first check at 10s"
          f"{', testing config off' if args.field_trial_config else ''}")

    found = run(args.binary, args.wait, args.headless, args.field_trial_config)
    allowed = read_allowed()

    print()
    if not found:
        print("  nothing downloaded")
    total = 0
    unexpected = []
    for name, size in sorted(found.items(), key=lambda kv: -kv[1]):
        total += size
        mark = " " if name in allowed else "!"
        print(f"  {mark} {int(size / 1024):>8} KB  {name}")
        if name not in allowed:
            unexpected.append(name)
    if found:
        print(f"    {int(total / 1024):>8} KB  total")

    if unexpected:
        print(f"\n{len(unexpected)} component(s) not on the allow list:")
        for name in unexpected:
            print(f"  {name}")
        if args.baseline:
            print("\nEvery download is a connection the user did not ask for."
                  " Either stop it, or add a line to"
                  f" {ALLOWED_FILE.relative_to(config.ROOT)} saying why it has"
                  " to stay.")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
