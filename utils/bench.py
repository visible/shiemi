#!/usr/bin/env python3
"""Measure the browser, so performance claims can be backed by numbers.

  python3 utils/bench.py                            # startup and memory
  python3 utils/bench.py --runs 7 startup
  python3 utils/bench.py speedometer jetstream motionmark
  python3 utils/bench.py --compare "C:\\Program Files\\...\\chrome.exe"

Nothing here may be quoted as a speedup on its own. A number is only worth
stating next to the same number from a stock build of the same Chromium
version, which is what --compare is for: it runs the identical suite against a
second binary and prints the difference.

Results are medians. A browser start is noisy enough that a mean gets dragged
around by one unlucky run, and the point of these figures is to survive
someone re-running them.
"""

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cdp
import config

DEFAULT_BINARY = config.CHROMIUM_SRC / "out" / "baseline" / "chrome.exe"

# First-run bubbles and the search picker would land in a paint timing. The
# backgrounding flags are required, not cosmetic: an unfocused window's
# renderer can stop being scheduled entirely, which hangs every call that
# needs it.
COMMON_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-search-engine-choice-screen",
    "--homepage=about:blank",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-background-timer-throttling",
]

# Cache files stay mapped after the browser dies, so copying them fails with a
# sharing violation, and a copied singleton marker makes the profile look
# occupied. Skipping them also gives every run an identical empty cache.
VOLATILE = shutil.ignore_patterns(
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
    "DawnWebGPUCache", "ShaderCache", "GrShaderCache", "Crashpad",
    "Singleton*", "*.lock", "lockfile",
)

STARTUP_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>startup</title>
<body style="background:#111;color:#eee;font:16px system-ui">
<h1>paint</h1>
"""

# Selectors break when browserbench rewrites its markup. Each expression
# returns a number when the run finishes and null while it is going, which is
# the only signal the poll loop gets.
WEB_BENCHMARKS = {
    "speedometer": {
        "url": "https://browserbench.org/Speedometer3.1/?startAutomatically=true",
        "unit": "runs/min",
        "higher_is_better": True,
        "score": """
            (() => {
              const el = document.querySelector('#result-number, .result-number');
              if (!el) return null;
              const v = parseFloat(el.textContent);
              return Number.isFinite(v) ? v : null;
            })()
        """,
    },
    "jetstream": {
        "url": "https://browserbench.org/JetStream2.2/?startAutomatically=true",
        "unit": "score",
        "higher_is_better": True,
        "score": """
            (() => {
              const el = document.querySelector('#result-summary .score, .score');
              if (!el) return null;
              const v = parseFloat(el.textContent);
              return Number.isFinite(v) ? v : null;
            })()
        """,
    },
    "motionmark": {
        "url": "https://browserbench.org/MotionMark1.3.1/?startAutomatically=true",
        "unit": "score",
        "higher_is_better": True,
        "score": """
            (() => {
              const el = document.querySelector('#results .score, .score');
              if (!el) return null;
              const v = parseFloat(el.textContent);
              return Number.isFinite(v) ? v : null;
            })()
        """,
    },
}


def process_rows() -> list:
    """Every process on the machine, with its parent and working set."""
    if sys.platform != "win32":
        return []
    script = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,WorkingSetSize | ConvertTo-Json"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    ).stdout
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) else [rows]


def tree_pids(rows, root_pid: int) -> set:
    children = {}
    for row in rows:
        children.setdefault(row["ParentProcessId"], []).append(row["ProcessId"])
    found, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        if pid in found:
            continue
        found.add(pid)
        stack.extend(children.get(pid, []))
    return found


def tree_memory_bytes(root_pid: int) -> int:
    """Summed working set of the browser and everything it spawned.

    Shared pages are counted once per process, so this reads high in absolute
    terms but still compares two builds fairly.
    """
    rows = process_rows()
    wanted = tree_pids(rows, root_pid)
    return sum(r["WorkingSetSize"] or 0 for r in rows if r["ProcessId"] in wanted)


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the browser and wait for its renderers to actually be gone.

    Killing the parent alone leaves renderers running, and taskkill returns
    before the tree has died.
    """
    doomed = tree_pids(process_rows(), proc.pid) or {proc.pid}
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not {r["ProcessId"] for r in process_rows()} & doomed:
            return
        time.sleep(0.5)


class Browser:
    """A running browser with DevTools attached, on a throwaway profile."""

    def __init__(self, binary: Path, profile: Path, urls, port: int = 9333):
        self.port = port
        self.launched_at_epoch_ms = time.time() * 1000
        self.proc = subprocess.Popen(
            [str(binary), f"--user-data-dir={profile}",
             f"--remote-debugging-port={port}", *COMMON_FLAGS, *urls],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def attach(self, timeout: float = 60.0):
        target = cdp.wait_for_page(self.port, time.monotonic() + timeout)
        if not target:
            raise RuntimeError("DevTools never came up")
        return cdp.Target(target["webSocketDebuggerUrl"])

    def close(self) -> None:
        kill_tree(self.proc)


def make_template(binary: Path, workspace: Path) -> Path:
    """A profile that has already been through first run.

    Runs get a copy, not a shared directory: a just-killed profile still looks
    occupied, so the next launch hands off to the instance it thinks is alive
    and exits without opening DevTools.
    """
    template = workspace / "template"
    browser = Browser(binary, template, ["about:blank"])
    try:
        browser.attach()
        time.sleep(2)
    finally:
        browser.close()
    return template


def start(binary: Path, template: Path, workspace: Path, tag: str, urls,
          timeout: float = 60.0):
    """Launch on a fresh copy of the template and attach, retrying once."""
    failure = None
    for attempt in range(2):
        profile = workspace / f"{tag}-{attempt}"
        shutil.rmtree(profile, ignore_errors=True)
        shutil.copytree(template, profile, ignore=VOLATILE)
        browser = Browser(binary, profile, urls)
        try:
            return browser, browser.attach(timeout)
        except Exception as exc:
            failure = exc
            browser.close()
            shutil.rmtree(profile, ignore_errors=True)
    raise RuntimeError(f"could not attach to {binary.name}: {failure}")


def new_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="shiemi-bench-"))


def measure_startup(binary: Path, runs: int) -> list:
    """Wall time from spawning the process to the first pixels of a page.

    Both ends are absolute instants on the same clock, so this script's own
    latency stays out of the number. Warm start: a cold one needs the file
    cache emptied, which means rebooting between runs.
    """
    workspace = new_workspace()
    page = workspace / "startup.html"
    page.write_text(STARTUP_PAGE, encoding="utf-8")
    try:
        template = make_template(binary, workspace)
        samples = []
        for i in range(runs):
            browser, target = start(binary, template, workspace, f"run{i}",
                                    [page.as_uri()])
            try:
                deadline = time.monotonic() + 60
                painted = None
                while time.monotonic() < deadline and painted is None:
                    painted = target.evaluate(
                        "(() => {"
                        "  const e = performance.getEntriesByName("
                        "    'first-contentful-paint')[0];"
                        "  return e ? performance.timeOrigin + e.startTime : null;"
                        "})()"
                    )
                    if painted is None:
                        time.sleep(0.05)
                if painted is None:
                    raise RuntimeError("page never painted")
                samples.append(painted - browser.launched_at_epoch_ms)
                target.close()
            finally:
                browser.close()
            print(f"    run {i + 1}/{runs}: {samples[-1]:.0f} ms")
        return samples
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def measure_memory(binary: Path, runs: int, tabs: int) -> list:
    """Footprint with a set of real pages open, after letting it settle."""
    urls = ["https://en.wikipedia.org/wiki/Browser_engine"] * tabs
    workspace = new_workspace()
    try:
        template = make_template(binary, workspace)
        samples = []
        for i in range(runs):
            browser, target = start(binary, template, workspace, f"run{i}", urls)
            try:
                # Loading finishes well before allocation settles.
                time.sleep(20)
                samples.append(tree_memory_bytes(browser.proc.pid) / (1024 * 1024))
                target.close()
            finally:
                browser.close()
            print(f"    run {i + 1}/{runs}: {samples[-1]:.0f} MB "
                  f"({samples[-1] / tabs:.0f} MB/tab)")
        return samples
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def measure_web(binary: Path, name: str, runs: int, timeout: float) -> list:
    spec = WEB_BENCHMARKS[name]
    workspace = new_workspace()
    try:
        template = make_template(binary, workspace)
        samples = []
        for i in range(runs):
            browser, target = start(binary, template, workspace, f"run{i}",
                                    [spec["url"]], timeout=120)
            try:
                deadline = time.monotonic() + timeout
                score = None
                while time.monotonic() < deadline and score is None:
                    try:
                        score = target.evaluate(spec["score"])
                    except RuntimeError:
                        score = None  # Page still navigating.
                    if score is None:
                        time.sleep(2)
                if score is None:
                    raise RuntimeError(
                        f"{name} produced no score in {timeout:.0f}s - the page "
                        "layout may have changed, check the selector"
                    )
                samples.append(float(score))
                target.close()
            finally:
                browser.close()
            print(f"    run {i + 1}/{runs}: {samples[-1]:.2f} {spec['unit']}")
        return samples
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_suite(binary: Path, names, runs: int, tabs: int, timeout: float) -> dict:
    print(f"\n=== {binary} ===")
    results = {}
    for name in names:
        print(f"  {name}")
        if name == "startup":
            results[name] = ("ms", False, measure_startup(binary, runs))
        elif name == "memory":
            results[name] = ("MB", False, measure_memory(binary, runs, tabs))
        else:
            spec = WEB_BENCHMARKS[name]
            results[name] = (spec["unit"], spec["higher_is_better"],
                             measure_web(binary, name, runs, timeout))
    return results


def report(mine: dict, theirs: dict) -> None:
    print("\n" + "=" * 64)
    for name, (unit, higher_better, samples) in mine.items():
        median = statistics.median(samples)
        spread = f"{min(samples):.1f}-{max(samples):.1f}" if len(samples) > 1 else "-"
        print(f"\n{name}  ({unit})")
        print(f"  this build {median:>10.1f}   range {spread}")
        if name not in theirs:
            continue
        other = statistics.median(theirs[name][2])
        print(f"  baseline   {other:>10.1f}")
        if other:
            change = (median - other) / other * 100
            better = change > 0 if higher_better else change < 0
            verdict = "better" if better else "worse"
            if abs(change) < 2:
                verdict = "no measurable difference"
            print(f"  delta      {change:>+9.1f}%   {verdict}")
    if not theirs:
        print("\nNo baseline was measured, so none of this is a speedup yet."
              "\nRe-run with --compare <stock chrome.exe> before quoting it.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("benchmarks", nargs="*", default=None,
                        help="startup, memory, " + ", ".join(WEB_BENCHMARKS))
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--compare", type=Path,
                        help="stock build to measure against")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--tabs", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=1800,
                        help="seconds to allow one web benchmark run")
    args = parser.parse_args()

    names = args.benchmarks or ["startup", "memory"]
    known = {"startup", "memory", *WEB_BENCHMARKS}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise SystemExit(f"unknown benchmark(s): {', '.join(unknown)}\n"
                         f"choose from: {', '.join(sorted(known))}")

    for path in filter(None, [args.binary, args.compare]):
        if not path.exists():
            raise SystemExit(f"no browser at {path}")

    mine = run_suite(args.binary, names, args.runs, args.tabs, args.timeout)
    theirs = {}
    if args.compare:
        theirs = run_suite(args.compare, names, args.runs, args.tabs, args.timeout)
    report(mine, theirs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
