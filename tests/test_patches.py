#!/usr/bin/env python3
"""Cover the patch-series checks that need no Chromium tree.

  python3 -m unittest discover -s tests

The series is validated in CI, where there is no checkout to apply it to, so
these checks read the patch text alone. That makes them the only thing standing
between a malformed patch and a rebase that fails hours into a build.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "utils"))

import build
import check_patches
import config


def diff_for(*paths: str) -> str:
    """Minimal patch text carrying just the headers the checks read."""
    return "".join(
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n"
        "@@ -1 +1 @@\n-old\n+new\n"
        for path in paths
    )


class SharedFiles(unittest.TestCase):
    def test_two_patches_one_file_is_reported(self):
        problems: list[str] = []
        owners: dict[str, str] = {}
        text = diff_for("chrome/browser/ui/thing.cc")
        check_patches.check_shared_files(owners, "a.patch", text, problems)
        check_patches.check_shared_files(owners, "b.patch", text, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("owned by a.patch", problems[0])

    def test_one_patch_touching_many_files_is_fine(self):
        problems: list[str] = []
        text = diff_for("a/one.cc", "a/two.cc", "a/three.cc")
        check_patches.check_shared_files({}, "a.patch", text, problems)
        self.assertEqual(problems, [])

    def test_the_same_patch_read_twice_does_not_report_itself(self):
        problems: list[str] = []
        owners: dict[str, str] = {}
        text = diff_for("a/one.cc")
        check_patches.check_shared_files(owners, "a.patch", text, problems)
        check_patches.check_shared_files(owners, "a.patch", text, problems)
        self.assertEqual(problems, [])

    def test_the_real_series_shares_nothing(self):
        """The check is only worth having if the series it guards passes it."""
        problems: list[str] = []
        owners: dict[str, str] = {}
        for entry in config.read_series():
            path = config.PATCHES_DIR / entry
            check_patches.check_shared_files(
                owners, entry, path.read_text(encoding="utf-8"), problems)
        self.assertEqual(problems, [])


class BrandingCollision(unittest.TestCase):
    """build.py copies art over the tree, so a patch there is discarded."""

    def test_a_patched_branding_file_is_reported(self):
        owned = next(iter(build.branded_paths()))
        problems: list[str] = []
        check_patches.check_branding_collision(
            "a.patch", diff_for(owned), problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("overwrites", problems[0])

    def test_an_ordinary_source_file_is_fine(self):
        problems: list[str] = []
        check_patches.check_branding_collision(
            "a.patch", diff_for("chrome/browser/ui/thing.cc"), problems)
        self.assertEqual(problems, [])

    def test_the_real_series_touches_none_of_them(self):
        problems: list[str] = []
        for entry in config.read_series():
            text = (config.PATCHES_DIR / entry).read_text(encoding="utf-8")
            check_patches.check_branding_collision(entry, text, problems)
        self.assertEqual(problems, [])

    def test_the_overlay_covers_the_icons_in_the_repo(self):
        """An empty mapping would make the check silently vacuous."""
        owned = build.branded_paths()
        self.assertTrue(owned)
        self.assertTrue(any(p.endswith(".ico") for p in owned))
        self.assertTrue(any(p.endswith(".icon") for p in owned))


class Series(unittest.TestCase):
    def test_every_entry_exists(self):
        for entry in config.read_series():
            self.assertTrue((config.PATCHES_DIR / entry).exists(), entry)

    def test_no_patch_uses_crlf(self):
        # git apply rejects these outright, and the error names a conflict.
        for entry in config.read_series():
            raw = (config.PATCHES_DIR / entry).read_bytes()
            self.assertNotIn(b"\r\n", raw, f"{entry} has CRLF line endings")

    def test_hunk_line_counts_match_their_headers(self):
        problems: list[str] = []
        for entry in config.read_series():
            text = (config.PATCHES_DIR / entry).read_text(encoding="utf-8")
            check_patches.check_hunks(entry, text, problems)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
