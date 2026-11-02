"""
Unit tests for HTML Graph Viewer (Milestone 11).
Verifies that render_viewer produces a zero-dependency self-contained HTML file
containing all entities, valid embedded JSON payload, and no external web references.
"""

from pathlib import Path
import json
import re
import tempfile
import unittest

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.pipeline import process_text
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.viewer import render_viewer
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


class TestGraphViewer(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry(include_auto=False)
        self.graph = StoryGraph.from_registry(self.registry)
        self.world = PrototypeWorld()

    def test_viewer_generation_and_integrity(self):
        """Viewer file exists, has no http/https links, contains all entity IDs, and valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            report = process_text(
                text=SAMPLE_SCRIPT,
                canon="hot_scoomp_main",
                run_id="viewer_test",
                out_dir=out_dir,
                graph=self.graph,
                world=self.world,
                learn=False,
            )

            html_file = out_dir / "viewer_test.viewer.html"
            self.assertTrue(html_file.exists(), "Viewer HTML file was not created.")

            content = html_file.read_text(encoding="utf-8")

            # Invariant 1: No external CDN or web script/link references
            # Matches any external http:// or https:// reference
            self.assertFalse(
                re.search(r'src=["\']https?://', content, re.IGNORECASE),
                "Viewer contains external script references.",
            )
            self.assertFalse(
                re.search(r'href=["\']https?://', content, re.IGNORECASE),
                "Viewer contains external stylesheet/font references.",
            )

            # Invariant 2: Contains every entity ID in run
            graph_data = json.loads((out_dir / "viewer_test.graph.json").read_text(encoding="utf-8"))
            for eid in graph_data.get("entities", []):
                self.assertIn(eid, content, f"Entity ID {eid} not found in HTML viewer.")

            # Invariant 3: Contains embedded script#data block and json.loads succeeds
            data_match = re.search(r'<script type="application/json" id="data">([\s\S]*?)</script>', content)
            self.assertIsNotNone(data_match, "Embedded <script id='data'> block not found in HTML.")

            parsed_data = json.loads(data_match.group(1))
            self.assertIn("run_graph", parsed_data)
            self.assertIn("report", parsed_data)
            self.assertEqual(parsed_data["run_graph"]["run_id"], "viewer_test")


if __name__ == "__main__":
    unittest.main()
