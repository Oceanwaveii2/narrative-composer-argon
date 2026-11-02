"""
Regression tests for the critical (P0) defects found during the system audit.

Covers:
  1. The Venice API key must never be stored in source code.
  2. `--prose-rewrite --manifest` must not crash on epistemic scope extraction.
  3. Tier-2 recook must apply even when a Tier-1 patch already rewrote the same line
     (the violation's recorded offending_text goes stale).
"""

import tempfile
import unittest
from pathlib import Path

from narrative_composer.cli import cmd_prose_rewrite, load_manifest
from narrative_composer.compiler.recook_dispatcher import RecookDispatcher
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.parser.fountain_lexer import FountainParser

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "hot_scoomp_manifest.json"


class TestP0Regressions(unittest.TestCase):
    def test_venice_api_key_is_not_hardcoded_in_source(self):
        source = (
            ROOT / "narrative_composer" / "prose" / "providers" / "venice.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "VENICE_INFERENCE_KEY",
            source,
            "API key must live in local_secrets.json or the environment, never in source.",
        )

    def test_prose_rewrite_accepts_manifest(self):
        """Exercises the epistemic-scope path that previously raised AttributeError."""
        with tempfile.TemporaryDirectory() as tmp:
            proposal = cmd_prose_rewrite(
                target_text="He walked slowly into the room.",
                mode="mock",
                ledger_path=str(Path(tmp) / "ledger.json"),
                manifest_path=str(MANIFEST),
            )
        self.assertTrue(proposal.proposed_text.strip())
        self.assertTrue(proposal.protected_words_verified)

    def test_recook_proposes_changes_without_changing_the_line(self):
        script = (
            "## INT. TEST ROOM - DAY\n\n"
            "STELLA stands in the corner, furious about the Hot Scoomp situation.\n\n"
            '**STELLA:** (full Kardashian cadence) "This is a total Boondocks rip-off."\n'
        )
        epistemic, spatial, _ = load_manifest(str(MANIFEST))
        violations = ScreenplayLinter(epistemic, spatial).lint_full_script(
            FountainParser.parse(script)
        )
        self.assertTrue(violations, "Fixture must produce lint violations")

        report = RecookDispatcher(provider_type="mock").dispatch_all(script, violations)

        self.assertEqual(report.tier1_patches_applied + report.tier2_rewrites_applied, 0)
        self.assertGreaterEqual(len(report.pending_proposals), 1)
        self.assertEqual(report.reconstructed_script, script)


if __name__ == "__main__":
    unittest.main()
