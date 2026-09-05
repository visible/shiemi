#!/usr/bin/env python3
"""Stop the two build configurations drifting apart.

  python3 -m unittest discover -s tests

flags/baseline.gn is what every patch is developed and measured against, and
flags/release.gn is what ships. Where they differ, the development build
describes a browser nobody gets, and nothing about that failure is loud: the
build succeeds and the browser runs.

It has already happened once. baseline.gn was missing proprietary_codecs, so
H.264 and AAC were absent from every build used to test patches, including the
fullscreen work, while playing normally in the shipped build.

So every argument in either file must either appear in both with the same
value, or be named below with the reason it is allowed to differ.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLAGS = ROOT / "flags"

# Arguments that legitimately differ, with why. Everything else has to match.
MAY_DIFFER = {
    "is_official_build": "carries PGO and LTO; tripling build time is the "
                         "whole reason a development configuration exists",
    "chrome_pgo_phase": "the development build opts out of PGO",
    "symbol_level": "symbols dominate link time",
    "blink_symbol_level": "symbols dominate link time",
    "v8_symbol_level": "symbols dominate link time",
}

ASSIGNMENT = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*(.+?)\s*$")


def read(name: str) -> dict:
    """Parse gn assignments, ignoring comments and blank lines.

    Both files are flat lists of scalar assignments, so this needs no gn.
    """
    args = {}
    for line in (FLAGS / f"{name}.gn").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(stripped)
        if match:
            args[match.group(1)] = match.group(2)
    return args


class Drift(unittest.TestCase):
    def setUp(self):
        self.baseline = read("baseline")
        self.release = read("release")

    def test_both_files_parse(self):
        self.assertIn("is_debug", self.baseline)
        self.assertIn("is_debug", self.release)

    def test_shared_arguments_agree(self):
        for name in set(self.baseline) & set(self.release):
            if name in MAY_DIFFER:
                continue
            self.assertEqual(
                self.baseline[name], self.release[name],
                f"{name} differs between the two configurations, so the "
                f"development build is not the browser that ships",
            )

    def test_no_argument_is_missing_from_one_side(self):
        for name in set(self.baseline) ^ set(self.release):
            self.assertIn(
                name, MAY_DIFFER,
                f"{name} is set in only one configuration. Either set it in "
                f"both or add it to MAY_DIFFER with the reason",
            )

    def test_privacy_arguments_are_in_both(self):
        """The ones whose absence is silent and costs us a shipped promise."""
        for name in ("disable_fieldtrial_testing_config", "enable_reporting",
                     "enable_remoting", "proprietary_codecs"):
            self.assertIn(name, self.baseline, f"{name} missing from baseline")
            self.assertIn(name, self.release, f"{name} missing from release")

    def test_every_exemption_carries_a_reason(self):
        for name, reason in MAY_DIFFER.items():
            self.assertTrue(reason, f"{name} is exempt with no reason given")

    def test_exemptions_are_all_still_used(self):
        """A stale exemption hides the next real drift."""
        declared = set(self.baseline) | set(self.release)
        for name in MAY_DIFFER:
            self.assertIn(
                name, declared,
                f"{name} is exempt but set in neither file; drop it",
            )


if __name__ == "__main__":
    unittest.main()
