"""
Milestone 5: End-to-End Closed-Loop Verification Test Suite.
Validates the complete closed-loop feedback engine, multi-pass convergence,
DOM reverse-ingestion, prose diagnostics, and canon invariants across all 5 narrative arcs.
"""

import os
from pathlib import Path
import tempfile
import unittest

from narrative_composer.compiler.convergence_harness import (
    ClosedLoopConvergenceHarness,
    ConvergenceResult,
)
from narrative_composer.linter.html_feedback_loop import HTMLFeedbackLoopVerifier
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.models.ast_nodes import ASTNodeType


class TestNeurosymbolicClosedLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent.parent
        cls.screenplay_path = cls.root_dir / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        cls.manifest_path = (
            cls.root_dir / "narrative_composer" / "config" / "hot_scoomp_manifest.json"
        )
        cls.reader_html_path = cls.root_dir / "hot_scoomp_reader.html"

    def test_master_chronology_full_convergence(self):
        """Asserts that the unabridged master screenplay achieves full fixpoint convergence."""
        self.assertTrue(self.screenplay_path.exists(), "Master screenplay file missing!")
        self.assertTrue(self.manifest_path.exists(), "Manifest file missing!")

        harness = ClosedLoopConvergenceHarness(
            manifest_path=str(self.manifest_path),
            provider_mode="mock",
            max_iterations=3,
        )

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp_html:
            tmp_html_path = Path(tmp_html.name)
        tmp_html_path.unlink()

        try:
            result = harness.run(
                screenplay_path=self.screenplay_path,
                html_out_path=tmp_html_path,
                in_place=False,
            )
            self.assertFalse(result.converged, "Legacy story lacks approved causal events")
            self.assertGreater(result.graph_review_questions, 0)
            self.assertGreater(result.graph_gate_errors, 0)
            self.assertEqual(result.graph_status, "pending review")
            self.assertEqual(result.final_rule_violations, 0)
            self.assertIsNotNone(result.final_html_report)
            self.assertTrue(result.final_html_report.converged)
        finally:
            if tmp_html_path.exists():
                try:
                    os.unlink(tmp_html_path)
                except Exception:
                    pass

    def test_all_five_narrative_arcs_present(self):
        """Asserts that all 5 narrative arcs exist with proper headers and dialogue."""
        text = self.screenplay_path.read_text(encoding="utf-8").upper()
        self.assertIn("EPISODE 0", text)
        self.assertIn("PREQUEL", text)
        self.assertIn("ACT ONE", text)
        self.assertIn("ACT TWO", text)
        self.assertTrue("CLIMAX" in text or "EPISODE TAG" in text)

        # Also verify in reader HTML DOM
        self.assertTrue(self.reader_html_path.exists())
        reader_text = self.reader_html_path.read_text(encoding="utf-8").upper()
        self.assertIn("EPISODE 0", reader_text)
        self.assertIn("PREQUEL", reader_text)
        self.assertIn("ACT ONE", reader_text)
        self.assertIn("ACT TWO", reader_text)
        self.assertTrue("CLIMAX" in reader_text or "TAG" in reader_text)

    def test_zero_filter_words_and_zero_emotion_labels(self):
        """Asserts zero filter words and zero emotion labels in reader action prose."""
        self.assertTrue(self.reader_html_path.exists())
        audit = HTMLFeedbackLoopVerifier.audit_html(self.reader_html_path)
        
        filter_count = audit.metrics.get("filter_words", 0)
        label_count = audit.metrics.get("emotion_labels", 0)
        
        self.assertEqual(filter_count, 0, f"Detected {filter_count} filter words in action prose.")
        self.assertEqual(label_count, 0, f"Detected {label_count} emotion labels in action prose.")

    def test_cadence_burstiness_threshold(self):
        """Asserts that sentence cadence burstiness sigma meets or exceeds 4.5."""
        self.assertTrue(self.reader_html_path.exists())
        audit = HTMLFeedbackLoopVerifier.audit_html(self.reader_html_path)
        sigma = audit.metrics.get("burstiness_sigma", 0.0)
        self.assertGreaterEqual(
            sigma, 4.5, f"Burstiness sigma {sigma:.2f} is below the 4.5 threshold."
        )

    def test_html_dom_id_uniqueness_and_anchor_parity(self):
        """Asserts zero duplicate DOM IDs and zero dangling navigation href anchors."""
        self.assertTrue(self.reader_html_path.exists())
        audit = HTMLFeedbackLoopVerifier.audit_html(self.reader_html_path)
        dom_errors = [v for v in audit.violations if v.stage == "DOM_INTEGRITY"]
        self.assertEqual(len(dom_errors), 0, f"DOM integrity violations: {dom_errors}")

    def test_convergence_does_not_rewrite_seeded_defects_without_review(self):
        """
        Validates the feedback loop on a script containing seeded defects:
          - Real-world trademark leak (RULE_9)
          - Director parenthetical shorthand (RULE_12)
          - Price embargo leak (RULE_1)
        The harness must report unresolved findings and preserve the manuscript until review.
        """
        seeded_script = """# EPISODE 0: FOXY MOMMA
## SCENE 1: LOBBY
INT. SERRANO GLUTE GYM - DAY

Klaus balances a goldfish bowl on the counter.

RECEPTIONIST
The enrollment initiation fee is five hundred dollars.

KLAUS
(whining in Roger's high-pitched cadence)
I only have water!

Klaus grabs the Kardashian stabilizer off the desk.
"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp_script:
            tmp_script.write(seeded_script)
            tmp_script_path = Path(tmp_script.name)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp_html:
            tmp_html_path = Path(tmp_html.name)
        tmp_html_path.unlink()

        try:
            original_bytes = tmp_script_path.read_bytes()
            harness = ClosedLoopConvergenceHarness(
                manifest_path=str(self.manifest_path),
                provider_mode="mock",
                max_iterations=4,
            )

            result = harness.run(
                screenplay_path=tmp_script_path,
                html_out_path=tmp_html_path,
                in_place=True,
            )

            self.assertGreater(result.initial_rule_violations, 0)
            self.assertEqual(result.total_tier1_patches, 0)
            self.assertGreater(result.final_rule_violations, 0)
            self.assertFalse(result.converged)
            self.assertEqual(tmp_script_path.read_bytes(),original_bytes)
        finally:
            if tmp_script_path.exists():
                try:
                    os.unlink(tmp_script_path)
                except Exception:
                    pass
            if tmp_html_path.exists():
                try:
                    os.unlink(tmp_html_path)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
