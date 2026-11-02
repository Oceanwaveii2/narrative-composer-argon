"""
Unit tests for Harness and Prompt Integration (Milestone 12).
Verifies advisory graph context injection into context projector and non-blocking
graph reporting in the closed-loop convergence harness.
"""

from pathlib import Path
import tempfile
import unittest

from narrative_composer.compiler.context_projector import graph_context_block
from narrative_composer.compiler.convergence_harness import ClosedLoopConvergenceHarness
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry


class TestGraphIntegration(unittest.TestCase):

    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.manifest_path = (
            self.root_dir / "narrative_composer" / "config" / "hot_scoomp_manifest.json"
        )
        self.registry = load_registry(include_auto=False)
        self.graph = StoryGraph.from_registry(self.registry)

    def test_graph_context_block_stella_standard(self):
        """graph_context_block returns nonempty context when called on Stella/standard, within max_chars."""
        ctx = graph_context_block(
            graph=self.graph,
            entities=["stella"],
            state_slugs={"stella": "standard"},
            canon="hot_scoomp_main",
            max_chars=1200,
        )

        self.assertIsInstance(ctx, str)
        self.assertGreater(len(ctx), 0)
        self.assertLessEqual(len(ctx), 1200)
        self.assertIn("STANDARD", ctx.upper())

    def test_graph_context_block_truncation(self):
        """Context block truncates cleanly with ellipsis if budget exceeded."""
        ctx = graph_context_block(
            graph=self.graph,
            entities=["stella"],
            state_slugs={"stella": "standard"},
            canon="hot_scoomp_main",
            max_chars=12,
        )

        self.assertLessEqual(len(ctx), 12)
        self.assertTrue(ctx.endswith("..."))

    def test_graph_context_block_resilience_to_unknown_entity(self):
        """Function returns without raising exception on unknown entity."""
        ctx = graph_context_block(
            graph=self.graph,
            entities=["unknown_character_xyz"],
            state_slugs={},
            canon="hot_scoomp_main",
            max_chars=500,
        )
        self.assertIsInstance(ctx, str)

    def test_harness_reports_graph_advisory_counts(self):
        """Convergence harness includes advisory graph errors, warnings, suggestions in summary."""
        test_script = """SCENE 1 - INT. LIVING ROOM - DAY

Stella stands near the couch.

STELLA
Where is the cube?
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f_scr:
            f_scr.write(test_script)
            scr_path = Path(f_scr.name)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f_html:
            html_path = Path(f_html.name)
        html_path.unlink()

        try:
            harness = ClosedLoopConvergenceHarness(
                manifest_path=str(self.manifest_path),
                provider_mode="mock",
                max_iterations=1,
            )
            result = harness.run(
                screenplay_path=scr_path,
                html_out_path=html_path,
                in_place=False,
            )

            self.assertIsInstance(result.graph_errors, int)
            self.assertIsInstance(result.graph_warnings, int)
            self.assertIsInstance(result.graph_suggestions, int)

            summary_text = result.summary()
            self.assertIn("Narrative Node Graph (passed)", summary_text)
            self.assertIn("Graph Errors:", summary_text)
            self.assertIn("Graph Warnings:", summary_text)
            self.assertIn("Graph Suggestions:", summary_text)
        finally:
            if scr_path.exists():
                scr_path.unlink()
            if html_path.exists():
                html_path.unlink()


if __name__ == "__main__":
    unittest.main()
