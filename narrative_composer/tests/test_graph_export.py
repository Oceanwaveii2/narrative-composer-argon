"""
Unit tests for Standalone Export and Import (M9).
Verifies path slicing, minimal EntityDef creation, ID immutability,
round-trip graph loading, and canon constraint enforcement.
"""

import unittest
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import Annotation
from narrative_composer.graph.world_port import PrototypeWorld
from narrative_composer.graph.export import export_standalone, import_standalone


class TestGraphExport(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)

    def test_export_stella_nerd_path(self):
        """Exporting stella nerd_20 -> nerd_80 yields 2 states and 1 transform with original IDs."""
        data = export_standalone(self.graph, "stella", "nerd_20", "nerd_80")

        self.assertEqual(data["kind"], "standalone_seed")
        self.assertEqual(data["schema_version"], 1)

        ent = data["entity"]
        self.assertEqual(ent["entity_id"], "stella")
        self.assertEqual(ent["base_state"], "nerd_20")

        # States: nerd_20, nerd_80
        states = ent["states"]
        self.assertEqual(len(states), 2)
        state_ids = {s["id"] for s in states}
        self.assertEqual(state_ids, {"stella.state.nerd_20", "stella.state.nerd_80"})

        # Transforms: nerd_20__nerd_80
        transforms = ent["transforms"]
        self.assertEqual(len(transforms), 1)
        self.assertEqual(transforms[0]["id"], "stella.xform.nerd_20__nerd_80")
        self.assertEqual(transforms[0]["from_state"], "stella.state.nerd_20")
        self.assertEqual(transforms[0]["to_state"], "stella.state.nerd_80")

        # Import standalone into StoryGraph and verify find_path
        imported_graph = import_standalone(data)
        path = imported_graph.find_path("stella.state.nerd_20", "stella.state.nerd_80")
        self.assertEqual(path, ["stella.xform.nerd_20__nerd_80"])

    def test_export_single_state(self):
        """Exporting a single state yields 1 state, 0 transforms."""
        data = export_standalone(self.graph, "stella", "nerd_20")

        ent = data["entity"]
        self.assertEqual(ent["entity_id"], "stella")
        self.assertEqual(ent["base_state"], "nerd_20")
        self.assertEqual(len(ent["states"]), 1)
        self.assertEqual(ent["states"][0]["id"], "stella.state.nerd_20")
        self.assertEqual(len(ent["transforms"]), 0)

        # Import into graph
        imported_graph = import_standalone(data)
        self.assertEqual(len(imported_graph.get_entity("stella").states), 1)
        self.assertEqual(len(imported_graph.get_entity("stella").transforms), 0)

    def test_ling_au_export_steve_states_raises_value_error(self):
        """A ling_au export of Steve states returns an empty path and raises ValueError."""
        # big_tiddy_steve is only valid in hot_scoomp_main, not ling_au
        with self.assertRaises(ValueError):
            export_standalone(
                self.graph,
                "stella",
                "nerd_80",
                "big_tiddy_steve",
                canon="ling_au",
            )

        with self.assertRaises(ValueError):
            export_standalone(
                self.graph,
                "stella",
                "big_tiddy_steve",
                canon="ling_au",
            )

    def test_export_with_annotations_and_world(self):
        """Active annotations targeting path IDs and world facts/relationships are exported."""
        ann = Annotation(
            id="ann.stella.state.nerd_20.1",
            target_id="stella.state.nerd_20",
            source="manual",
            kind="visual",
            text="Polo shirt popping.",
            tags=["polo"],
        )
        self.graph.annotations[ann.id] = ann

        world = PrototypeWorld()
        data = export_standalone(
            self.graph,
            "stella",
            "nerd_20",
            "nerd_80",
            include_annotations=True,
            world=world,
        )

        self.assertIn("ann.stella.state.nerd_20.1", data["annotations"])
        self.assertIn("world", data)
        self.assertIn("relationships", data["world"])
        self.assertIn("facts", data["world"])

        imported = import_standalone(data)
        self.assertIn("ann.stella.state.nerd_20.1", imported.annotations)


if __name__ == "__main__":
    unittest.main()
