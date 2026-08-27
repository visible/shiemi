#!/usr/bin/env python3
"""Check the patch series without needing a Chromium checkout.

  python3 utils/check_patches.py

Catches the failures that only show up hours into a build: a series entry
with no file behind it, a patch nobody applies, CRLF endings that make
git apply reject a clean tree, and hunk headers whose counts no longer match
the body after a hand edit.
"""

import re
import sys

import config

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def check_series(problems: list[str]) -> list[str]:
    entries = config.read_series()

    seen = set()
    for entry in entries:
        if entry in seen:
            problems.append(f"series: {entry} listed twice")
        seen.add(entry)
        if not (config.PATCHES_DIR / entry).exists():
            problems.append(f"series: {entry} has no file")

    on_disk = {
        p.relative_to(config.PATCHES_DIR).as_posix()
        for p in config.PATCHES_DIR.rglob("*.patch")
    }
    for orphan in sorted(on_disk - seen):
        problems.append(f"{orphan}: on disk but not in series")

    return entries


def check_endings(entry: str, raw: bytes, problems: list[str]) -> None:
    if b"\r\n" in raw:
        problems.append(
            f"{entry}: CRLF line endings, git apply will reject this"
        )
    if raw and not raw.endswith(b"\n"):
        problems.append(f"{entry}: no trailing newline")


def check_hunks(entry: str, text: str, problems: list[str]) -> None:
    """Verify every hunk body matches the line counts in its @@ header."""
    lines = text.splitlines()
    files = sum(1 for line in lines if line.startswith("diff --git "))
    if not files:
        problems.append(f"{entry}: no diff --git header, not a git patch")
        return

    hunks = 0
    i = 0
    while i < len(lines):
        match = HUNK.match(lines[i])
        if not match:
            i += 1
            continue

        hunks += 1
        want_old = int(match.group(2) or 1)
        want_new = int(match.group(4) or 1)
        got_old = got_new = 0

        i += 1
        while i < len(lines):
            line = lines[i]
            if line.startswith("@@") or line.startswith("diff --git "):
                break
            # "\ No newline at end of file" annotates the line above it.
            if line.startswith("\\"):
                i += 1
                continue
            head = line[:1]
            if head == "+":
                got_new += 1
            elif head == "-":
                got_old += 1
            elif head in (" ", ""):
                got_old += 1
                got_new += 1
            else:
                break
            i += 1

        if (got_old, got_new) != (want_old, want_new):
            problems.append(
                f"{entry}: hunk at {match.group(0)} counts "
                f"{got_old},{got_new} but declares {want_old},{want_new}"
            )

    if not hunks:
        problems.append(f"{entry}: no hunks")


def main() -> int:
    problems: list[str] = []
    entries = check_series(problems)

    for entry in entries:
        path = config.PATCHES_DIR / entry
        if not path.exists():
            continue
        raw = path.read_bytes()
        check_endings(entry, raw, problems)
        check_hunks(entry, raw.decode("utf-8", "replace"), problems)

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"{len(entries)} patch(es) ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
