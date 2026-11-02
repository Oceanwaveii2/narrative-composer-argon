"""
Unit tests for Semantic Context Enrichment and World Port (Milestone 6).
"""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.graph.enrich import attach, load_annotations, semantic_context
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import Annotation
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.world_port import PrototypeWorld, WorldStateProvider


class FakeWorld:
    """Mock implementation of WorldStateProvider for testing protocol conformance."""

    def relationships(self, entity_id: str, scene_index=None, canon=None):
        return [{"a": entity_id, "b": "partner", "kind": "test_rel"}]

    def facts(self, entity_id: str, scene_index=None, canon=None):
        return [{"entity": entity_id, "fact": "tested"}]

    def location(self, entity_id: str, scene_index=None):
        return "Test Room"


class TestGraphEnrich(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)

    def test_attach_and_semantic_context(self):
        ann = Annotation(
            id="ann.stella.state.nerd_20.1",
            target_id="stella.state.nerd_20",
            source="manual_test",
            kind="lore",
            text="First stage of mathematical obsession. Button popping occurs.",
            confidence=0.95,
        )
        attach(self.graph, ann)

        ctx = semantic_context(self.graph, "stella.state.nerd_20")
        self.assertEqual(ctx["target"], "stella.state.nerd_20")
        self.assertEqual(len(ctx["annotations"]), 1)
        self.assertIn("mathematical obsession", ctx["text"])
        self.assertIn("stella.state.standard", ctx["neighbors"]["previous"])
        self.assertIn("stella.state.nerd_80", ctx["neighbors"]["next"])

    def test_max_chars_truncation(self):
        long_text = "Detailed backstory lore sentence. " * 50
        ann = Annotation(
            id="ann.rainee.state.base.1",
            target_id="rainee.state.base",
            source="long_test",
            kind="lore",
            text=long_text,
            confidence=1.0,
        )
        attach(self.graph, ann)

        ctx = semantic_context(self.graph, "rainee.state.base", max_chars=150)
        self.assertLessEqual(len(ctx["text"]), 150)
        self.assertTrue(ctx["text"].endswith("..."))

    def test_load_annotations_skips_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "annotations.json"
            data = [
                {
                    "id": "ann.haley.state.standard.1",
                    "target_id": "haley.state.standard",
                    "source": "seed",
                    "kind": "visual",
                    "text": "Wears vintage cargo shorts and peace pendant.",
                    "confidence": 0.8,
                },
                {
                    "id": "ann.haley.state.standard.1",  # duplicate ID
                    "target_id": "haley.state.standard",
                    "source": "duplicate",
                    "kind": "visual",
                    "text": "Duplicate should be ignored.",
                    "confidence": 0.5,
                },
                {
                    "id": "ann.haley.state.standard.2",
                    "target_id": "haley.state.standard",
                    "source": "seed",
                    "kind": "lore",
                    "text": "Dating Jeff Fischer in his van.",
                    "confidence": 0.9,
                },
            ]
            p.write_text(json.dumps(data), encoding="utf-8")

            added = load_annotations(self.graph, p)
            self.assertEqual(added, 2)
            self.assertIn("ann.haley.state.standard.1", self.graph.annotations)
            self.assertIn("ann.haley.state.standard.2", self.graph.annotations)

    def test_deprecated_annotations_excluded(self):
        ann = Annotation(
            id="ann.holly.state.base.dep",
            target_id="holly.state.base",
            source="dep_test",
            kind="note",
            text="Old note that is now deprecated.",
            status="deprecated",
        )
        self.graph.annotations[ann.id] = ann

        ctx = semantic_context(self.graph, "holly.state.base")
        self.assertEqual(len(ctx["annotations"]), 0)
        self.assertNotIn("Old note", ctx["text"])

    def test_world_state_protocol_and_prototype(self):
        # Verify FakeWorld satisfies WorldStateProvider protocol
        fake = FakeWorld()
        self.assertIsInstance(fake, WorldStateProvider)
        self.assertEqual(fake.location("stella"), "Test Room")

        # Verify PrototypeWorld implementation
        world = PrototypeWorld()
        self.assertIsInstance(world, WorldStateProvider)

        # Check Holly/Haley relationship in hot_scoomp_main
        holly_rels = world.relationships("holly", canon="hot_scoomp_main")
        self.assertTrue(any(r["b"] == "haley" and r["kind"] == "girlfriend" for r in holly_rels))

        # Check Kelly/Francine in hot_scoomp_main
        kelly_rels = world.relationships("kelly", canon="hot_scoomp_main")
        self.assertTrue(any(r["b"] == "francine" and r["kind"] == "friend" for r in kelly_rels))

        # Check Ma Ma Ling / Francine in ling_au
        mama_rels = world.relationships("ma_ma_ling", canon="ling_au")
        self.assertTrue(any(r["b"] == "francine" and r["kind"] == "mother_of" for r in mama_rels))

    def test_import_boundary_enforcement(self):
        # Strict rule: graph.py, extract.py, kernel.py must NOT import PrototypeWorld
        forbidden_files = [
            Path(__file__).resolve().parent.parent / "graph" / "graph.py",
            Path(__file__).resolve().parent.parent / "graph" / "extract.py",
            Path(__file__).resolve().parent.parent / "graph" / "kernel.py",
        ]
        for fpath in forbidden_files:
            content = fpath.read_text(encoding="utf-8")
            self.assertNotIn(
                "PrototypeWorld",
                content,
                f"Forbidden import of PrototypeWorld found in {fpath.name}",
            )


if __name__ == "__main__":
    unittest.main()
