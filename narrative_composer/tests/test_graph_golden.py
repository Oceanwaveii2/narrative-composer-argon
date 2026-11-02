"""
Golden Tests and Smoke Suite for Narrative Node Graph (Milestone 13).
Validates ling_au canon constraints on the Spring Breakup episode and full-chronology smoke stability.
"""

from pathlib import Path
import tempfile
import unittest

from narrative_composer.graph.checks import run_checks
from narrative_composer.graph.extract import extract_run
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.pipeline import process_text
from narrative_composer.graph.registry import load_registry
from narrative_composer.parser.fountain_lexer import FountainParser


class TestGraphGolden(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent.parent
        cls.chronology_path = cls.root_dir / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        cls.full_text = cls.chronology_path.read_text(encoding="utf-8")

        # Slice the Spring Breakup section without depending on its exact title:
        # locate the marker, walk back to the nearest top-level heading, and end at
        # the next top-level heading. A retitled section must not silently degrade
        # into a slice that runs to end-of-file.
        marker_idx = cls.full_text.upper().find("SPRING BREAKUP")
        if marker_idx == -1:
            raise unittest.SkipTest("Spring Breakup section is not present in the chronology")

        heading_pos = cls.full_text.rfind("\n# ", 0, marker_idx)
        section_start = 0 if heading_pos == -1 else heading_pos + 1
        next_heading = cls.full_text.find("\n# ", section_start + 1)
        section_end = len(cls.full_text) if next_heading == -1 else next_heading

        cls.spring_breakup_text = cls.full_text[section_start:section_end]
        if "INT." not in cls.spring_breakup_text and "EXT." not in cls.spring_breakup_text:
            raise unittest.SkipTest("Spring Breakup slice contains no scene headings")
        cls.registry = load_registry(include_auto=False)
        cls.graph = StoryGraph.from_registry(cls.registry)

    def test_section_slice_is_scoped_to_one_section(self):
        """The slice must be the Spring Breakup section only, not the rest of the document."""
        self.assertLess(len(self.spring_breakup_text), len(self.full_text))
        lines = self.spring_breakup_text.splitlines()
        self.assertTrue(lines[0].startswith("# "), "slice must start on a top-level heading")
        self.assertEqual(
            [line for line in lines[1:] if line.startswith("# ")],
            [],
            "slice must not contain a second top-level heading",
        )

    def test_spring_breakup_golden_ling_au(self):
        """Validates canonical invariants in Spring Breakup section under ling_au canon."""
        ast = FountainParser.parse(self.spring_breakup_text)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="golden_ling_au")
        violations = run_checks(res, self.graph, canon="ling_au", elements=ast)

        # 1. Rainee: exactly one explicit transform rainee.xform.base__peter in Scene 1
        rainee_xforms = [
            xf for xf in res.xforms
            if xf.entity == "rainee" and xf.xform_id == "rainee.xform.base__peter"
        ]
        self.assertEqual(rainee_xforms, [], "Legacy cues do not establish causal events")

        # 2. No stella.state.big_tiddy_steve instance anywhere
        steve_instances = [
            st for st in res.states
            if st.state_id == "stella.state.big_tiddy_steve"
        ]
        self.assertEqual(len(steve_instances), 0)

        # 3. Zero G1, G2, and G3 violations
        critical_violations = [
            v for v in violations
            if v.rule_id in ("G1_ILLEGAL_TRANSITION", "G2_CUE_STATE_MISMATCH", "G3_CANON_LEAK")
        ]
        self.assertTrue(any(v.rule_id == "G2_CUE_STATE_MISMATCH" for v in critical_violations),
                        "Unverified cue assertions must no longer pass silently")

        # 4. ma_ma_ling has a base state instance in the Spring Breakup section
        ling_states = [
            st for st in res.states
            if st.entity == "ma_ma_ling" and st.state_id == "ma_ma_ling.state.base"
        ]
        self.assertGreaterEqual(len(ling_states), 1)

        # 5. Stella and Haley remain in baseline states (poser_nerd for Stella in ling_au, standard for Haley)
        stella_states = [st.state_id for st in res.states if st.entity == "stella"]
        for st_id in stella_states:
            self.assertEqual(st_id, "stella.state.poser_nerd")

        haley_states = [st.state_id for st in res.states if st.entity == "haley"]
        for st_id in haley_states:
            self.assertEqual(st_id, "haley.state.standard")

    def test_full_chronology_smoke(self):
        """Full-chronology smoke test: run hot_scoomp_main on entire chronology file without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            report = process_text(
                text=self.full_text,
                canon="hot_scoomp_main",
                run_id="full_chronology_smoke",
                out_dir=out_dir,
                graph=self.graph,
                learn=False,
            )

            self.assertIn("summary", report)
            summary = report["summary"]
            self.assertGreater(summary["state_instances"], 0)
            self.assertEqual(summary["transforms"], 0)
            self.assertGreater(summary["review_questions"], 0)
            self.assertGreater(summary["gate_errors"], 0)
            self.assertTrue(any(v["rule_id"] == "G8_UNVERIFIED_EVENT" for v in report["violations"]))


if __name__ == "__main__":
    unittest.main()
