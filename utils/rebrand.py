"""Rewrite the product name in Chromium's branded string tables.

chrome/app/chromium_strings.grd hardcodes the product name in over 800 places.
Carrying that as a patch would mean re-resolving hundreds of hunks every rebase,
so it runs as a build step instead. The operation is idempotent and rewrites the
file only when something actually changed.

Only the text inside <message> bodies is touched. Names, desc attributes and
comments are left alone so that nothing but user-visible text moves.

Attribution stays: "The Chromium Authors" and chromium.org links are the
upstream copyright and its documentation, and removing either would be a
licence violation rather than branding.
"""

import re
import subprocess
from pathlib import Path

PRODUCT = "Shiemi"

KEEP = re.compile(r"Chromium Authors|chromium\.org|Chromium OS|ChromiumOS")

MESSAGE = re.compile(r"(<message\b[^>]*>)(.*?)(</message>)", re.DOTALL)

# Only the Chromium-branded table. google_chrome_strings.grd is never compiled
# in an unbranded build, and components_strings.grd refers to the product
# through a placeholder that resolves to IDS_PRODUCT_NAME.
TARGETS = ["chrome/app/chromium_strings.grd"]


def rewrite(path: Path, product: str = PRODUCT) -> int:
    """Rename the product inside message bodies. Returns messages changed."""
    original = path.read_text(encoding="utf-8")
    changed = 0

    def replace(match: re.Match) -> str:
        nonlocal changed
        head, body, tail = match.groups()
        if "Chromium" not in body:
            return match.group(0)
        rebranded = "".join(
            line if KEEP.search(line) else line.replace("Chromium", product)
            for line in body.splitlines(keepends=True)
        )
        if rebranded != body:
            changed += 1
        return head + rebranded + tail

    updated = MESSAGE.sub(replace, original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return changed


def restore(src: Path, relative: str) -> None:
    """Put the upstream file back before rewriting it.

    The rewrite looks for "Chromium", so running it twice is a no-op and a
    changed PRODUCT would otherwise leave the previous name in place. This step
    owns the file outright, so discarding local edits to it is intended.
    """
    subprocess.run(
        ["git", "-C", str(src), "checkout", "--", relative],
        capture_output=True,
        check=False,
    )


def apply(src: Path, product: str = PRODUCT) -> int:
    total = 0
    for relative in TARGETS:
        path = src / relative
        if path.exists():
            restore(src, relative)
            total += rewrite(path, product)
    return total
