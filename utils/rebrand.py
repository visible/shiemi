"""Rewrite the product name in Chromium's branded string tables.

The product name is hardcoded in thousands of strings: some as "Chromium",
which a branded build swaps out, and many more as "Chrome" outright, which no
build configuration touches. The second kind is why the padlock bubble, the
error pages and the autofill prompts all still said Chrome. Carrying that as a
patch would mean re-resolving thousands of hunks every rebase, so it runs as a
build step instead. The operation is idempotent and rewrites a file only when
something actually changed.

Only the text inside <message> bodies is touched. Names, desc attributes and
comments are left alone so that nothing but user-visible text moves.

Renaming a string changes the id grit hashes it under, so its existing
translations no longer match and non-English locales fall back to this English
text. That is the price of the rename and it applies to every string here.

Attribution stays: "The Chromium Authors" and chromium.org links are the
upstream copyright and its documentation, and removing either would be a
licence violation rather than branding.
"""

import fnmatch
import re
import subprocess
from pathlib import Path

PRODUCT = "Shiemi"

KEEP = re.compile(r"Chromium Authors|chromium\.org|Chromium OS|ChromiumOS")

# Bare "Chrome" in prose means "the browser you are using", so it moves. What
# stays is the set of separate Google products that merely share the name: the
# browser itself, the store, the CA program, the sync service, the enterprise
# line and the remote desktop app are none of them this browser, and a string
# naming one is stating a fact rather than branding. ChromeOS needs no guard,
# since the trailing \b already fails on it.
KEEP_CHROME = (
    "Web Store", "Webstore", "OS", "Root Store", "Canary", "Sync", "Android",
    "Enterprise", "Browser Cloud", "Remote Desktop",
)
CHROME = re.compile(
    r"(?<!Google )\bChrome\b(?!\s+(?:" + "|".join(KEEP_CHROME) + r")\b)"
)

MESSAGE = re.compile(r"(<message\b[^>]*>)(.*?)(</message>)", re.DOTALL)

# google_chrome_strings.grd is never compiled in an unbranded build, and
# components_strings.grd holds no strings of its own - all 68 of its part files
# do, and between them they own the omnibox, page info, permission prompts,
# autofill, the error pages and the interstitials.
#
# The two chrome/app part files are separate from the main table and easy to
# miss: settings_chromium_strings names the About page in the settings menu,
# and settings_strings carries the body of every settings page.
#
# No patch may touch a file matched here, because each one is restored from
# upstream before it is rewritten. check_patches.py enforces that.
TARGETS = [
    "chrome/app/chromium_strings.grd",
    "chrome/app/generated_resources.grd",
    "chrome/app/settings_chromium_strings.grdp",
    "chrome/app/settings_strings.grdp",
    "components/*_strings.grdp",
]


def rewrite(path: Path, product: str = PRODUCT) -> int:
    """Rename the product inside message bodies. Returns messages changed."""
    original = path.read_text(encoding="utf-8")
    changed = 0

    def replace(match: re.Match) -> str:
        nonlocal changed
        head, body, tail = match.groups()
        if "Chromium" not in body and "Chrome" not in body:
            return match.group(0)
        rebranded = "".join(
            line if KEEP.search(line)
            else CHROME.sub(product, line.replace("Chromium", product))
            for line in body.splitlines(keepends=True)
        )
        if rebranded != body:
            changed += 1
        return head + rebranded + tail

    updated = MESSAGE.sub(replace, original)
    if updated != original:
        # newline="" keeps the LF endings the tree uses; the default would
        # rewrite every line on Windows and bury the real change.
        path.write_text(updated, encoding="utf-8", newline="")
    return changed


def restore(src: Path, relative: str) -> None:
    """Put the upstream file back before rewriting it.

    The rewrite looks for the upstream names, so running it twice is a no-op and
    a changed PRODUCT would otherwise leave the previous name in place. This
    step owns the file outright, so discarding local edits to it is intended.
    """
    subprocess.run(
        ["git", "-C", str(src), "checkout", "--", relative],
        capture_output=True,
        check=False,
    )


def owns(relative: str) -> bool:
    """Whether this build step owns the file, so no patch may touch it.

    Pattern matching rather than a directory listing, so the check runs without
    a Chromium checkout.
    """
    return any(fnmatch.fnmatch(relative, pattern) for pattern in TARGETS)


def resolve(src: Path) -> list[str]:
    paths = []
    for pattern in TARGETS:
        if "*" in pattern:
            paths += sorted(p.relative_to(src).as_posix()
                            for p in src.glob(pattern))
        elif (src / pattern).exists():
            paths.append(pattern)
    return paths


def apply(src: Path, product: str = PRODUCT) -> int:
    total = 0
    for relative in resolve(src):
        restore(src, relative)
        total += rewrite(src / relative, product)
    return total
