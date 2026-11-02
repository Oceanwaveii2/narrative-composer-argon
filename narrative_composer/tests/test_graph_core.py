"""
Unit tests for Narrative Node Graph Core, Patching, and Migrations (Milestone 3).
"""

import tempfile
import unittest
from pathlib import Path

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.migrations import MIGRATIONS, migrate, register_migration
from narrative_composer.graph.patch import PatchError, apply_patch
from narrative_composer.graph.registry import load_registry


class TestGraphCore(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)

    def test_find_path_hot_scoomp_main(self):
        # In hot_scoomp_main, Stella has 3 sequential transformations: standard -> nerd_20 -> nerd_80 -> big_tiddy_steve
        path = self.graph.find_path(
            "stella.state.standard",
            "stella.state.big_tiddy_steve",
            canon="hot_scoomp_main",
        )
        expected = [
            "stella.xform.standard__nerd_20",
            "stella.xform.nerd_20__nerd_80",
            "stella.xform.nerd_80__big_tiddy_steve",
        ]
        self.assertEqual(path, expected)

    def test_find_path_ling_au_returns_none(self):
        # In ling_au, big_tiddy_steve is scoped out, so no path should exist
        path = self.graph.find_path(
            "stella.state.standard",
            "stella.state.big_tiddy_steve",
            canon="ling_au",
        )
        self.assertIsNone(path)

    def test_patch_add_intermediate_state_and_find_path(self):
        # Add nerd_50 between nerd_20 and nerd_80
        patch_ops = [
            {
                "op": "add_state",
                "entity": "stella",
                "state": {
                    "id": "stella.state.nerd_50",
                    "slug": "nerd_50",
                    "label": "Dork transformation 50%",
                    "order": 1,
                    "canons": ["hot_scoomp_main"],
                },
            },
            {
                "op": "add_xform",
                "entity": "stella",
                "xform": {
                    "id": "stella.xform.nerd_20__nerd_50",
                    "from_state": "stella.state.nerd_20",
                    "to_state": "stella.state.nerd_50",
                    "canons": ["hot_scoomp_main"],
                },
            },
            {
                "op": "add_xform",
                "entity": "stella",
                "xform": {
                    "id": "stella.xform.nerd_50__nerd_80",
                    "from_state": "stella.state.nerd_50",
                    "to_state": "stella.state.nerd_80",
                    "canons": ["hot_scoomp_main"],
                },
            },
        ]

        patched_graph = apply_patch(self.graph, patch_ops, author="test_author")
        self.assertIn("stella.state.nerd_50", [s.id for s in patched_graph.entities["stella"].states])

        # Test path traversing through the new intermediate state
        path_50 = patched_graph.find_path(
            "stella.state.nerd_20",
            "stella.state.nerd_80",
            canon="hot_scoomp_main",
        )
        # Original direct xform is 1 hop, so BFS finds direct or intermediate
        self.assertIsNotNone(path_50)

        # Deprecate the direct transform nerd_20__nerd_80
        deprecate_op = [{"op": "deprecate", "target_id": "stella.xform.nerd_20__nerd_80"}]
        rerouted_graph = apply_patch(patched_graph, deprecate_op)
        rerouted_path = rerouted_graph.find_path(
            "stella.state.nerd_20",
            "stella.state.nerd_80",
            canon="hot_scoomp_main",
        )
        expected_reroute = [
            "stella.xform.nerd_20__nerd_50",
            "stella.xform.nerd_50__nerd_80",
        ]
        self.assertEqual(rerouted_path, expected_reroute)

    def test_deprecate_hides_from_states_of(self):
        states_before = [s.id for s in self.graph.states_of("stella")]
        self.assertIn("stella.state.nerd_20", states_before)

        patch_ops = [{"op": "deprecate", "target_id": "stella.state.nerd_20"}]
        patched = apply_patch(self.graph, patch_ops)

        states_after = [s.id for s in patched.states_of("stella")]
        self.assertNotIn("stella.state.nerd_20", states_after)

    def test_bad_patch_leaves_graph_unmutated(self):
        original_states = [s.id for s in self.graph.entities["stella"].states]
        original_changelog_len = len(self.graph.changelog)

        bad_patch = [
            {
                "op": "add_state",
                "entity": "stella",
                "state": {
                    "id": "stella.state.valid_state",
                    "slug": "valid_state",
                    "label": "Valid",
                },
            },
            {
                "op": "add_state",
                "entity": "stella",
                "state": {
                    "id": "stella.state.invalid..id",
                    "slug": "invalid",
                    "label": "Invalid",
                },
            },
        ]

        with self.assertRaises(PatchError):
            apply_patch(self.graph, bad_patch)

        # Ensure no partial state was applied
        current_states = [s.id for s in self.graph.entities["stella"].states]
        self.assertEqual(current_states, original_states)
        self.assertEqual(len(self.graph.changelog), original_changelog_len)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test_graph.json"
            self.graph.save(p)
            loaded = StoryGraph.load(p)

            self.assertEqual(sorted(self.graph.entities.keys()), sorted(loaded.entities.keys()))
            for eid in self.graph.entities:
                self.assertEqual(
                    [s.id for s in self.graph.entities[eid].states],
                    [s.id for s in loaded.entities[eid].states],
                )

    def test_schema_migration(self):
        # Register a fake migration from version 0 to 1
        def fake_v0_to_v1(data):
            data["schema_version"] = 1
            data["migrated_marker"] = True
            return data

        register_migration(0, fake_v0_to_v1)
        old_data = {"schema_version": 0, "entities": {}}
        migrated = migrate(old_data, target_version=1)
        self.assertEqual(migrated["schema_version"], 1)
        self.assertTrue(migrated["migrated_marker"])


if __name__ == "__main__":
    unittest.main()
