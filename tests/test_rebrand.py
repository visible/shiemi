#!/usr/bin/env python3
"""Pin the product rename rules.

  python3 -m unittest discover -s tests

The rename runs over roughly ten thousand strings on every build, so a rule
that is slightly too greedy is not something a screenshot will catch. The
interesting cases are the ones that must not move: a string naming a separate
Google product is stating a fact, and rewriting it makes the browser lie.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))

import rebrand


def rename(text: str) -> str:
    """Run one line through the same path rewrite() takes."""
    if rebrand.KEEP.search(text):
        return text
    return rebrand.CHROME.sub(
        rebrand.PRODUCT, text.replace("Chromium", rebrand.PRODUCT))


class Renames(unittest.TestCase):
    def test_prose_moves(self):
        for before, after in [
            ("Chrome is out of date", "Shiemi is out of date"),
            ("Let Chrome choose", "Let Shiemi choose"),
            ("Chrome Panels", "Shiemi Panels"),
            ("Chrome Autofill saved this", "Shiemi Autofill saved this"),
            ("Remove from Chrome", "Remove from Shiemi"),
            ("About Chromium", "About Shiemi"),
            ("Chrome's performance", "Shiemi's performance"),
        ]:
            self.assertEqual(rename(before), after)

    def test_other_products_stay(self):
        for text in [
            "Go to Google Chrome help",
            "Open Chrome Web Store",
            "Chrome Webstore",
            "Chrome OS device",
            "ChromeOS device",
            "The Chrome Root Store",
            "Chrome Sync is off",
            "Chrome Enterprise Core",
            "Chrome Browser Cloud Management",
            "Chrome Remote Desktop",
            "Chrome Android",
        ]:
            self.assertEqual(rename(text), text, f"{text} should not move")

    def test_attribution_stays(self):
        for text in [
            "Copyright 2026 The Chromium Authors",
            "Visit https://chromium.org for more",
            "Chromium OS",
        ]:
            self.assertEqual(rename(text), text, f"{text} should not move")

    def test_identifiers_and_urls_stay(self):
        # Uppercase ids and lowercase URLs are the two forms that appear inside
        # message bodies without being prose.
        for text in [
            "IDS_SETTINGS_SIDE_PANEL_ALIGNMENT_CHROME_PANELS",
            "chrome://settings/appearance",
            "https://support.google.com/chrome/answer/1",
        ]:
            self.assertEqual(rename(text), text, f"{text} should not move")

    def test_idempotent(self):
        once = rename("Chrome updated Chrome to the latest Chromium")
        self.assertEqual(rename(once), once)


class Rewrite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).resolve().parent / "_rebrand_tmp.grd"
        self.addCleanup(self.tmp.unlink, missing_ok=True)

    def write(self, text: str) -> None:
        self.tmp.write_text(text, encoding="utf-8", newline="")

    def test_only_message_bodies_move(self):
        self.write(
            '<grit>\n'
            '  <!-- Chrome comment stays -->\n'
            '  <message name="IDS_A" desc="Chrome desc stays">\n'
            '    Chrome moves\n'
            '  </message>\n'
            '</grit>\n'
        )
        self.assertEqual(rebrand.rewrite(self.tmp), 1)
        out = self.tmp.read_text(encoding="utf-8")
        self.assertIn("Chrome comment stays", out)
        self.assertIn('desc="Chrome desc stays"', out)
        self.assertIn("Shiemi moves", out)

    def test_line_endings_survive(self):
        self.write('<message name="IDS_A">\n  Chrome\n</message>\n')
        rebrand.rewrite(self.tmp)
        self.assertNotIn(b"\r\n", self.tmp.read_bytes())

    def test_untouched_file_is_not_rewritten(self):
        self.write('<message name="IDS_A">\n  Nothing to do\n</message>\n')
        before = self.tmp.stat().st_mtime_ns
        self.assertEqual(rebrand.rewrite(self.tmp), 0)
        self.assertEqual(self.tmp.stat().st_mtime_ns, before)


class WholeBodyReplacement(unittest.TestCase):
    """The publisher name moves; the copyright notice beside it must not."""

    GRD = (
        '<message name="IDS_ABOUT_VERSION_COMPANY_NAME" desc="Company name">\n'
        '  The Chromium Authors\n'
        '</message>\n'
        '<message name="IDS_ABOUT_VERSION_COPYRIGHT" desc="Copyright">\n'
        '  Copyright 2026 The Chromium Authors. All rights reserved.\n'
        '</message>\n'
    )

    def rewrite(self, text: str) -> str:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        path = root / "chromium_strings.grd"
        path.write_text(text, encoding="utf-8")
        rebrand.rewrite(path)
        return path.read_text(encoding="utf-8")

    def test_company_name_becomes_the_product(self):
        out = self.rewrite(self.GRD)
        self.assertIn(f"  {rebrand.PRODUCT}\n</message>", out)
        self.assertNotIn("The Chromium Authors\n</message>", out)

    def test_the_copyright_notice_survives(self):
        out = self.rewrite(self.GRD)
        self.assertIn(
            "Copyright 2026 The Chromium Authors. All rights reserved.", out)

    def test_indentation_is_preserved(self):
        out = self.rewrite(self.GRD)
        self.assertIn(f'desc="Company name">\n  {rebrand.PRODUCT}\n', out)

    def test_running_twice_changes_nothing(self):
        once = self.rewrite(self.GRD)
        self.assertEqual(self.rewrite(once), once)

    def test_the_description_loses_the_safe_browsing_claim(self):
        out = self.rewrite(
            '<message name="IDS_PRODUCT_DESCRIPTION" desc="Browser">\n'
            "  Chromium is a web browser. Browse the web more safely with"
            " malware and phishing protection built into Chromium.\n"
            "</message>\n")
        self.assertNotIn("phishing", out)
        self.assertNotIn("malware", out)
        self.assertIn(rebrand.PRODUCT, out)

    def test_every_replacement_names_the_product(self):
        for name, text in rebrand.REPLACE_WHOLE.items():
            self.assertIn(rebrand.PRODUCT, text, name)


class Resolve(unittest.TestCase):
    """A pattern that matches nothing must stop the build, not the strings."""

    def tree(self, *relative: str) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for name in relative:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<message>Chrome</message>", encoding="utf-8")
        return root

    def test_a_complete_tree_resolves(self):
        root = self.tree(*[p for p in rebrand.TARGETS if "*" not in p],
                         "components/one_strings.grdp")
        self.assertEqual(len(rebrand.resolve(root)), len(rebrand.TARGETS))

    def test_a_missing_literal_target_raises(self):
        root = self.tree("components/one_strings.grdp")
        with self.assertRaises(SystemExit) as caught:
            rebrand.resolve(root)
        self.assertIn("not in", str(caught.exception))

    def test_a_glob_matching_nothing_raises(self):
        root = self.tree(*[p for p in rebrand.TARGETS if "*" not in p])
        with self.assertRaises(SystemExit) as caught:
            rebrand.resolve(root)
        self.assertIn("matches nothing", str(caught.exception))


class Ownership(unittest.TestCase):
    def test_owned(self):
        for path in [
            "chrome/app/generated_resources.grd",
            "chrome/app/settings_strings.grdp",
            "components/autofill_strings.grdp",
            "components/omnibox_pedal_ui_strings.grdp",
        ]:
            self.assertTrue(rebrand.owns(path), f"{path} should be owned")

    def test_not_owned(self):
        for path in [
            "chrome/browser/ui/toolbar/app_menu_model.cc",
            "components/components_strings.grd",
            "chrome/app/theme/chromium/BRANDING",
        ]:
            self.assertFalse(rebrand.owns(path), f"{path} should be free")


if __name__ == "__main__":
    unittest.main()
