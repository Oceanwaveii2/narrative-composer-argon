"""
Milestone 1 Test Suite: Symbolic Schemas, FSM State Machines, and Manifest Validation.
Runs via standard library unittest (no external test runner dependencies needed).
"""

import json
import os
import unittest

from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.epistemic import (
    EpistemicBelief,
    EpistemicMatrix,
    FactCategory,
    NarrativeFact,
)
from narrative_composer.models.spatial_fsm import (
    BodySlot,
    ItemLifecycle,
    PhysicalEntity,
    SpatialGraph,
)
from narrative_composer.models.causal_dag import (
    CausalDAG,
    StoryBeatNode,
    StateDelta,
)


class TestEpistemicMatrix(unittest.TestCase):
    def setUp(self):
        self.matrix = EpistemicMatrix()
        self.fact_steve = NarrativeFact(
            fact_id="fact_steve_identity",
            category=FactCategory.IDENTITY,
            canonical_text="Francine wishes she had a son named Steve.",
            embargo_tokens=["Steve", "Steven", "Big Tiddy Steve"]
        )
        self.matrix.facts[self.fact_steve.fact_id] = self.fact_steve

    def test_default_belief_is_unknown(self):
        belief = self.matrix.get_belief("STELLA", "fact_steve_identity")
        self.assertEqual(belief, EpistemicBelief.UNKNOWN)

    def test_embargo_tokens_active_when_unknown(self):
        embargoes = self.matrix.get_embargoed_tokens_for_character("STELLA")
        self.assertIn("steve", embargoes)
        self.assertIn("steven", embargoes)
        self.assertIn("big tiddy steve", embargoes)

    def test_embargo_lifted_when_fact_known(self):
        self.matrix.set_belief("STELLA", "fact_steve_identity", EpistemicBelief.KNOWN_TRUE)
        self.assertEqual(self.matrix.get_belief("STELLA", "fact_steve_identity"), EpistemicBelief.KNOWN_TRUE)
        embargoes = self.matrix.get_embargoed_tokens_for_character("STELLA")
        self.assertNotIn("steve", embargoes)

    def test_case_insensitivity_for_character_names(self):
        self.matrix.set_belief("stella", "fact_steve_identity", EpistemicBelief.KNOWN_TRUE)
        self.assertEqual(self.matrix.get_belief("STELLA", "fact_steve_identity"), EpistemicBelief.KNOWN_TRUE)
        self.assertEqual(self.matrix.get_belief("Stella", "fact_steve_identity"), EpistemicBelief.KNOWN_TRUE)


class TestSpatialFSM(unittest.TestCase):
    def test_button_charge_depletion(self):
        buttons = PhysicalEntity(
            item_id="stella_polo_buttons",
            name="Stella's Polo Buttons",
            lifecycle=ItemLifecycle.EQUIPPED,
            room_id="living_room",
            charges_remaining=6,
            max_charges=6
        )
        # Pop top 2 collar buttons
        ok = buttons.pop_charges(2)
        self.assertTrue(ok)
        self.assertEqual(buttons.charges_remaining, 4)
        self.assertEqual(buttons.lifecycle, ItemLifecycle.DAMAGED)

        # Pop remaining 4 torso buttons
        ok = buttons.pop_charges(4)
        self.assertTrue(ok)
        self.assertEqual(buttons.charges_remaining, 0)
        self.assertEqual(buttons.lifecycle, ItemLifecycle.EXPENDED)

        # Attempt to pop another button (should fail)
        ok = buttons.pop_charges(1)
        self.assertFalse(ok)
        self.assertEqual(buttons.charges_remaining, 0)

    def test_lamp_shatter_and_zombie_prevention(self):
        lamp = PhysicalEntity(
            item_id="gloria_lamp",
            name="Gloria the Flamingo Lamp",
            lifecycle=ItemLifecycle.DORMANT,
            room_id="living_room"
        )
        self.assertTrue(lamp.shatter("Smashed into pink ceramic shards."))
        self.assertEqual(lamp.lifecycle, ItemLifecycle.DESTROYED)

        # Attempt to shatter again (zombie destruction prevented)
        self.assertFalse(lamp.shatter("Smashed again."))

    def test_spatial_accessibility(self):
        spatial = SpatialGraph(
            character_locations={
                "STELLA": "living_room",
                "ZOOEY": "upstairs_bedroom"
            },
            items={
                "gloria_lamp": PhysicalEntity(
                    item_id="gloria_lamp",
                    name="Gloria the Flamingo Lamp",
                    lifecycle=ItemLifecycle.DORMANT,
                    room_id="living_room"
                ),
                "nail_file": PhysicalEntity(
                    item_id="nail_file",
                    name="Zooey's Nail File",
                    lifecycle=ItemLifecycle.DRAWN,
                    room_id="upstairs_bedroom",
                    held_by="ZOOEY"
                )
            }
        )
        # Stella in living room can access Gloria
        self.assertTrue(spatial.assert_prop_accessible("STELLA", "gloria_lamp"))
        # Stella cannot access nail file in upstairs bedroom
        self.assertFalse(spatial.assert_prop_accessible("STELLA", "nail_file"))
        # Zooey can access her nail file
        self.assertTrue(spatial.assert_prop_accessible("ZOOEY", "nail_file"))


class TestCausalDAG(unittest.TestCase):
    def test_topological_actionable_progression(self):
        dag = CausalDAG(
            beats={
                "beat_1": StoryBeatNode(
                    beat_id="beat_1",
                    chunk_index=0,
                    beat_order=1,
                    slugline="INT. BEDROOM",
                    active_characters=["STELLA"],
                    dramatic_goal="Stella spikes highlighter.",
                    prerequisite_beat_ids=[]
                ),
                "beat_2": StoryBeatNode(
                    beat_id="beat_2",
                    chunk_index=1,
                    beat_order=2,
                    slugline="INT. LIVING ROOM",
                    active_characters=["STELLA", "HAYLEY"],
                    dramatic_goal="Hayley smashes lamp.",
                    prerequisite_beat_ids=["beat_1"]
                )
            }
        )
        # Beat 1 should be immediately actionable
        next_beat = dag.get_next_actionable_beat()
        self.assertIsNotNone(next_beat)
        self.assertEqual(next_beat.beat_id, "beat_1")

        # Mark Beat 1 completed
        dag.mark_completed("beat_1", "STELLA: Show time.")
        self.assertTrue(dag.beats["beat_1"].is_completed)

        # Now Beat 2 should become actionable
        next_beat = dag.get_next_actionable_beat()
        self.assertIsNotNone(next_beat)
        self.assertEqual(next_beat.beat_id, "beat_2")

        # Complete Beat 2
        dag.mark_completed("beat_2", "HAYLEY: Oops.")
        self.assertTrue(dag.is_all_completed())
        self.assertIsNone(dag.get_next_actionable_beat())


class TestManifestLoading(unittest.TestCase):
    def test_manifest_loads_and_validates(self):
        manifest_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "config",
            "hot_scoomp_manifest.json"
        )
        self.assertTrue(os.path.exists(manifest_path), f"Manifest not found at {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate Facts
        facts = {k: NarrativeFact(**v) for k, v in data["facts"].items()}
        self.assertIn("fact_steve_identity", facts)
        self.assertIn("fact_rocket_ships", facts)
        self.assertIn("fact_gloria_broken", facts)

        # Validate Epistemic Matrix
        matrix = EpistemicMatrix(facts=facts)
        for char, beliefs in data["initial_beliefs"].items():
            for fact_id, val in beliefs.items():
                matrix.set_belief(char, fact_id, EpistemicBelief(val))

        # Initial checks on beliefs
        self.assertEqual(matrix.get_belief("STELLA", "fact_steve_identity"), EpistemicBelief.UNKNOWN)
        self.assertEqual(matrix.get_belief("FRANCINE", "fact_steve_identity"), EpistemicBelief.KNOWN_TRUE)

        # Validate Props
        props = {k: PhysicalEntity(**v) for k, v in data["props"].items()}
        self.assertEqual(props["stella_polo_buttons"].charges_remaining, 6)
        self.assertEqual(props["gloria_lamp"].lifecycle, ItemLifecycle.DORMANT)

        # Validate Spatial Graph
        spatial = SpatialGraph(
            items=props,
            character_locations=data["character_locations"],
            room_topology=data["room_topology"]
        )
        self.assertEqual(spatial.get_character_room("STELLA"), "upstairs_bedroom")
        self.assertEqual(spatial.get_character_room("HAYLEY"), "living_room")

        # Validate Causal DAG
        beats = {k: StoryBeatNode(**v) for k, v in data["beats"].items()}
        dag = CausalDAG(beats=beats)
        self.assertEqual(len(dag.beats), 6)
        first_beat = dag.get_next_actionable_beat()
        self.assertIsNotNone(first_beat)
        self.assertEqual(first_beat.beat_id, "cold_open")


if __name__ == "__main__":
    unittest.main()
