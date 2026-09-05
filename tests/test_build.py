#!/usr/bin/env python3
"""Make sure the build steps that write into the tree fail loudly.

  python3 -m unittest discover -s tests

Three steps reach into the Chromium checkout: branding art is copied over,
our WebUI tokens are appended, and the string tables are rewritten. Each one
used to skip quietly when its destination was absent, which is the worst
possible behaviour, because a rebase is exactly when a path moves and the
result still builds and runs. The browser would just ship upstream's icons,
upstream's blue palette, or strings that still say Chrome.

These tests point the steps at an empty tree and require them to complain.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "utils"))

import build
import fetch_ublock


class EmptyTree(unittest.TestCase):
    def setUp(self):
        self.src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.src, True)

    def test_branding_overlay_refuses_a_tree_with_nowhere_to_copy(self):
        with self.assertRaises(SystemExit) as caught:
            build.overlay_branding(self.src)
        self.assertIn("no directory in the tree", str(caught.exception))

    def test_style_overlay_refuses_a_missing_destination(self):
        with self.assertRaises(SystemExit) as caught:
            build.append_styles(self.src)
        self.assertIn("not in the tree", str(caught.exception))


class StyleOverlay(unittest.TestCase):
    def setUp(self):
        self.src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.src, True)
        for relative in build.STYLE_OVERLAYS.values():
            dest = self.src.joinpath(*relative.split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("html { color: red }\n", encoding="utf-8")

    def test_appends_once_and_is_idempotent(self):
        self.assertEqual(build.append_styles(self.src),
                         len(build.STYLE_OVERLAYS))
        self.assertEqual(build.append_styles(self.src), 0)

    def test_keeps_what_was_already_there(self):
        build.append_styles(self.src)
        relative = next(iter(build.STYLE_OVERLAYS.values()))
        text = self.src.joinpath(*relative.split("/")).read_text()
        self.assertIn("html { color: red }", text)
        self.assertIn(build.STYLE_BEGIN, text)
        self.assertIn(build.STYLE_END, text)

    def test_replaces_a_stale_block_rather_than_stacking(self):
        build.append_styles(self.src)
        relative = next(iter(build.STYLE_OVERLAYS.values()))
        dest = self.src.joinpath(*relative.split("/"))
        dest.write_text(
            dest.read_text().replace(build.STYLE_END,
                                     f"stale\n{build.STYLE_END}"),
            encoding="utf-8")
        build.append_styles(self.src)
        text = dest.read_text()
        self.assertEqual(text.count(build.STYLE_BEGIN), 1)
        self.assertNotIn("stale", text)


class BrandedPaths(unittest.TestCase):
    def test_every_owned_path_has_a_file_behind_it(self):
        for relative, source in build.branded_paths().items():
            self.assertTrue(source.is_file(), relative)

    def test_paths_are_tree_relative_and_posix(self):
        for relative in build.branded_paths():
            self.assertNotIn("\\", relative)
            self.assertFalse(relative.startswith("/"))


class BundledBlocker(unittest.TestCase):
    """The blocker's id is written down twice and must not drift.

    initial_preferences pins the toolbar icon by id, and the id is fixed by
    whichever key signed the release. If a future release is signed with a
    different key, the pin silently points at nothing: the blocker still
    works, its icon is just gone, which is the kind of thing nobody notices.
    """

    def test_the_pinned_id_is_the_one_being_shipped(self):
        defaults = json.loads(
            (ROOT / "defaults" / "initial_preferences").read_text("utf-8"))
        self.assertEqual(defaults["extensions"]["pinned_extensions"],
                         [fetch_ublock.EXTENSION_ID])

    def test_the_pins_agree_with_each_other(self):
        self.assertIn(fetch_ublock.VERSION, fetch_ublock.URL)
        self.assertEqual(len(fetch_ublock.SHA256), 64)
        self.assertEqual(len(fetch_ublock.EXTENSION_ID), 32)
        self.assertTrue(fetch_ublock.EXTENSION_ID.islower())


if __name__ == "__main__":
    unittest.main()
