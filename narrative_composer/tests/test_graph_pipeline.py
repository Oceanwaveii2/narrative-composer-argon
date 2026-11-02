"""
Unit tests for Narrative Node Graph Pipeline (Milestone 10).
Verifies automated node network construction, 3-artifact output generation,
network re-cooking from chain.json, and byte-identical reproducibility.
"""

from pathlib import Path
import json
import tempfile
import unittest

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.kernel import Network
from narrative_composer.graph.nodes import NODE_TYPES
from narrative_composer.graph.pipeline import (
    build_network_for_text,
    cook_network_to_report,
    process_text,
)
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.world_port import PrototypeWorld


SAMPLE_SCRIPT = """SCENE 1 - INT. DORM ROOM - NIGHT

Stella stands near the window, her fur bristling.

STELLA
We have to be careful with the cube.

Haley adjusts her blue dress and rolls her eyes.

HALEY
Relax, Stella. Nothing will happen.

The pink cube pulses with energy. Stella transforms into 80% nerd. Her glasses appear and she snorts.

STELLA
Now look what you did!
"""


class TestGraphPipeline(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)
        self.world = PrototypeWorld()

    def test_process_text_writes_three_files(self):
        """process_text creates chain.json, graph.json, and report.json in out_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            report = process_text(
                text=SAMPLE_SCRIPT,
                canon="hot_scoomp_main",
                run_id="sample_run",
                out_dir=out_dir,
                graph=self.graph,
                world=self.world,
                learn=False,
            )

            chain_path = out_dir / "sample_run.chain.json"
            graph_path = out_dir / "sample_run.graph.json"
            report_path = out_dir / "sample_run.report.json"

            self.assertTrue(chain_path.exists())
            self.assertTrue(graph_path.exists())
            self.assertTrue(report_path.exists())

            self.assertIn("summary", report)
            self.assertIn("discoveries", report)
            self.assertIn("violations", report)
            self.assertIn("suggestions", report)
            self.assertGreater(report["summary"]["state_instances"], 0)

    def test_chain_can_be_loaded_and_recooked(self):
        """chain.json can be loaded with Network.from_dict and recooked to the same report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            report1 = process_text(
                text=SAMPLE_SCRIPT,
                canon="hot_scoomp_main",
                run_id="recook_run",
                out_dir=out_dir,
                graph=self.graph,
                world=self.world,
                learn=False,
            )

            chain_path = out_dir / "recook_run.chain.json"
            chain_data = json.loads(chain_path.read_text(encoding="utf-8"))

            loaded_net = Network.from_dict(chain_data, NODE_TYPES)
            ctx = {"graph": StoryGraph.from_registry(self.registry), "world": self.world}

            _, report2, _, _ = cook_network_to_report(
                net=loaded_net,
                canon="hot_scoomp_main",
                run_id="recook_run",
                ctx=ctx,
            )

            self.assertEqual(report1["summary"], report2["summary"])
            self.assertEqual(len(report1["violations"]), len(report2["violations"]))
            self.assertEqual(len(report1["suggestions"]), len(report2["suggestions"]))

    def test_idempotent_byte_identical_output(self):
        """Running process_text twice produces byte-identical files."""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            out_dir1 = Path(tmpdir1)
            out_dir2 = Path(tmpdir2)

            process_text(
                text=SAMPLE_SCRIPT,
                canon="hot_scoomp_main",
                run_id="identical_test",
                out_dir=out_dir1,
                graph=self.graph,
                world=self.world,
                learn=False,
            )

            process_text(
                text=SAMPLE_SCRIPT,
                canon="hot_scoomp_main",
                run_id="identical_test",
                out_dir=out_dir2,
                graph=self.graph,
                world=self.world,
                learn=False,
            )

            for artifact in ["chain.json", "graph.json", "report.json"]:
                f1 = out_dir1 / f"identical_test.{artifact}"
                f2 = out_dir2 / f"identical_test.{artifact}"
                self.assertEqual(
                    f1.read_bytes(),
                    f2.read_bytes(),
                    f"Artifact {artifact} was not byte-identical across runs",
                )


if __name__ == "__main__":
    unittest.main()
