#!/usr/bin/env python3
"""Pin the release gates and the files they read.

  python3 -m unittest discover -s tests

Three gates decide whether a build is fit to ship: which hosts it contacts,
what it downloads, and whether the shipped defaults arrive. Each one reads a
hand-maintained file, and a gate that silently stops checking is worse than no
gate, because the green result is still printed. These tests cover the parsing
and the shape of those files, which is the part that can rot without a build.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "utils"))

import audit_components
import check_defaults


class AllowList(unittest.TestCase):
    def test_parses_name_and_reason(self):
        allowed = audit_components.read_allowed()
        self.assertIn("CertificateRevocation", allowed)
        self.assertTrue(allowed["CertificateRevocation"])

    def test_every_entry_carries_a_reason(self):
        """The file's own rule: an entry without an argument is a leak."""
        for name, reason in audit_components.read_allowed().items():
            self.assertTrue(reason, f"{name} is allowed with no reason given")

    def test_comments_and_blanks_are_ignored(self):
        allowed = audit_components.read_allowed()
        self.assertFalse(any(name.startswith("#") for name in allowed))
        self.assertFalse(any(not name.strip() for name in allowed))

    def test_caches_are_not_treated_as_components(self):
        """A cache holds copies of what arrived, so counting it double-counts."""
        for name in ["component_crx_cache", "extensions_crx_cache",
                     "GPUPersistentCache", "Default"]:
            self.assertIn(name, audit_components.NOT_COMPONENTS)

    def test_no_component_is_both_allowed_and_ignored(self):
        overlap = set(audit_components.read_allowed()) & \
            audit_components.NOT_COMPONENTS
        self.assertFalse(overlap, f"listed twice with opposite meanings: {overlap}")


class NetworkAllowList(unittest.TestCase):
    PATH = ROOT / "tests" / "network-allowed.txt"

    def hosts(self) -> list:
        lines = self.PATH.read_text(encoding="utf-8").splitlines()
        return [line.split("#", 1)[0].strip() for line in lines
                if line.split("#", 1)[0].strip()]

    def test_only_bare_hosts(self):
        """A scheme or a path here would never match and would pass silently."""
        for host in self.hosts():
            self.assertNotIn("/", host, f"{host} is not a bare host")
            self.assertNotIn(":", host, f"{host} is not a bare host")

    def test_stays_short(self):
        # Not a style rule. Every host is a connection the user did not ask
        # for, and the list growing quietly is the thing to notice.
        self.assertLessEqual(len(self.hosts()), 3, self.hosts())


class ShippedDefaults(unittest.TestCase):
    PATH = ROOT / "defaults" / "initial_preferences"

    def prefs(self) -> dict:
        return json.loads(self.PATH.read_text(encoding="utf-8"))

    def test_is_valid_json(self):
        # Chromium does not report a parse failure: first run finds no usable
        # file and every default silently reverts to upstream's.
        self.assertIsInstance(self.prefs(), dict)

    def test_flatten_produces_dotted_paths(self):
        flat = check_defaults.flatten(self.prefs())
        self.assertEqual(flat["safebrowsing.enabled"], False)
        self.assertEqual(flat["profile.cookie_controls_mode"], 1)
        self.assertEqual(flat["lens.policy.lens_overlay_settings"], 1)

    def test_flatten_keeps_lists_whole(self):
        """A list is a value, not a level: pinned_actions must stay a list."""
        flat = check_defaults.flatten({"toolbar": {"pinned_actions": []}})
        self.assertEqual(flat, {"toolbar.pinned_actions": []})

    def test_documented_in_the_readme(self):
        """Every default needs its argument written down next to it."""
        readme = (ROOT / "defaults" / "README.md").read_text(encoding="utf-8")
        for path in check_defaults.flatten(self.prefs()):
            leaf = path.rsplit(".", 1)[-1]
            self.assertIn(leaf, readme, f"{path} is set but never explained")


class Lookup(unittest.TestCase):
    def test_finds_nested_value(self):
        prefs = {"a": {"b": {"c": 7}}}
        self.assertEqual(check_defaults.lookup(prefs, "a.b.c"), 7)

    def test_missing_path_raises(self):
        with self.assertRaises(KeyError):
            check_defaults.lookup({"a": {"b": 1}}, "a.c")

    def test_scalar_midway_raises(self):
        # Guards against reporting a pref as present when its parent is a bool.
        with self.assertRaises(KeyError):
            check_defaults.lookup({"a": True}, "a.b")

    def test_false_is_found_not_treated_as_missing(self):
        """Most shipped defaults are false, so this is the common case."""
        self.assertEqual(check_defaults.lookup({"a": {"b": False}}, "a.b"), False)


if __name__ == "__main__":
    unittest.main()
