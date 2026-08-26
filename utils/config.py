"""Shared paths and settings.

The Chromium checkout is a build input that lives outside this repo. Point
SHIEMI_CHROMIUM_SRC at it to override the default.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATCHES_DIR = ROOT / "patches"
SERIES_FILE = PATCHES_DIR / "series"
FLAGS_DIR = ROOT / "flags"
VERSION_FILE = ROOT / "chromium_version.txt"

CHROMIUM_SRC = Path(os.environ.get("SHIEMI_CHROMIUM_SRC", r"E:\cr\src"))


def pinned_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def require_src() -> Path:
    if not (CHROMIUM_SRC / "chrome" / "VERSION").exists():
        raise SystemExit(
            f"no Chromium checkout at {CHROMIUM_SRC}\n"
            "set SHIEMI_CHROMIUM_SRC to the path of your checkout"
        )
    return CHROMIUM_SRC


def checkout_version() -> str:
    parts = {}
    for line in (CHROMIUM_SRC / "chrome" / "VERSION").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            parts[k.strip()] = v.strip()
    return "{MAJOR}.{MINOR}.{BUILD}.{PATCH}".format(**parts)


def read_series() -> list[str]:
    if not SERIES_FILE.exists():
        raise SystemExit(f"missing series file: {SERIES_FILE}")
    entries = []
    for raw in SERIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries
