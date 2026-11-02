"""
Milestone 2 Test Suite: Body Transformation State Machine & Environmental Debris FSM.
Validates:
1. DebrisHazard lifecycle (spawning on prop destruction, room-level hazard tracking, cleanup).
2. Rule 7: Debris hazard safety (barefoot movement across uncleared shards).
3. AnatomicalStage transitions for Hayley and Stella.
4. Rule 8: Anatomical persona consistency (Big Tiddy Steve nerd mannerisms, BBL Influencer vanity).
5. Full screenplay continuity with M1 + M2 rules active.
"""

from pathlib import Path
import unittest

from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.spatial_fsm import (
    SpatialGraph,
    PhysicalEntity,
    ItemLifecycle,
    AnatomicalStage,
    DebrisHazard,
)
from narrative_composer.models.epistemic import EpistemicMatrix
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.linter.rules import LinterRuleEngine


class TestDebrisHazardFSM(unittest.TestCase):
    def setUp(self):
        self.spatial = SpatialGraph(
            character_locations={"FRANCINE": "living_room", "STELLA": "living_room"}
        )

    def test_spawn_and_clear_debris_hazard(self):
        hazard = self.spatial.add_debris(
            hazard_id="gloria_lamp_shards",
            source_item_id="gloria_lamp",
            room_id="living_room",
            material="ceramic_shards"
        )
        self.assertEqual(hazard.hazard_id, "gloria_lamp_shards")
        self.assertFalse(hazard.is_cleared)

        active = self.spatial.get_active_hazards_in_room("living_room")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].hazard_id, "gloria_lamp_shards")

        cleared = self.spatial.clear_debris("gloria_lamp_shards", "FRANCINE")
        self.assertTrue(cleared)
        self.assertEqual(len(self.spatial.get_active_hazards_in_room("living_room")), 0)

    def test_rule7_flags_barefoot_movement_on_uncleared_shards(self):
        self.spatial.add_debris("gloria_lamp_shards", "gloria_lamp", "living_room", "ceramic_shards")

        action_node = ASTElement(
            node_type=ASTNodeType.ACTION,
            content="Francine walks barefoot across the carpet, reaching for her wine glass.",
            line_number=100
        )
        violation = LinterRuleEngine.check_debris_hazard_safety(
            action_node, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "RULE_7_DEBRIS_HAZARD_SAFETY")
        self.assertIn("ceramic_shards", violation.diagnostic_message)

    def test_rule7_passes_when_stepping_carefully_around_debris(self):
        self.spatial.add_debris("gloria_lamp_shards", "gloria_lamp", "living_room", "ceramic_shards")

        action_node = ASTElement(
            node_type=ASTNodeType.ACTION,
            content="Francine tiptoes barefoot, stepping over the ceramic shards on the floor.",
            line_number=101
        )
        violation = LinterRuleEngine.check_debris_hazard_safety(
            action_node, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNone(violation, "Action acknowledging and stepping over shards must pass")

    def test_rule7_passes_when_wearing_shoes(self):
        self.spatial.add_debris("gloria_lamp_shards", "gloria_lamp", "living_room", "ceramic_shards")

        action_node = ASTElement(
            node_type=ASTNodeType.ACTION,
            content="Roger marches across the living room in his six-inch patent-leather heels.",
            line_number=102
        )
        violation = LinterRuleEngine.check_debris_hazard_safety(
            action_node, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNone(violation, "Shod movement must not trigger barefoot debris hazard")


class TestBodyTransformationState(unittest.TestCase):
    def setUp(self):
        self.spatial = SpatialGraph()

    def test_hayley_stage_progression_history(self):
        self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_STANDARD)
        self.assertEqual(self.spatial.get_character_stage("HAYLEY"), AnatomicalStage.HAYLEY_STANDARD)

        self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_ROGER_DOME)
        self.assertEqual(self.spatial.get_character_stage("HAYLEY"), AnatomicalStage.HAYLEY_ROGER_DOME)

        self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_BBL_INFLUENCER)
        self.assertEqual(self.spatial.get_character_stage("HAYLEY"), AnatomicalStage.HAYLEY_BBL_INFLUENCER)

        anatomy = self.spatial.character_anatomies["HAYLEY"]
        self.assertEqual(len(anatomy.stage_history), 3)

    def test_rule8_stella_big_tiddy_steve_persona_mismatch(self):
        self.spatial.set_character_stage("STELLA", AnatomicalStage.STELLA_BIG_TIDDY_STEVE)

        mismatch_node = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I'm way too cool for this, you're such a dork.",
            speaker="STELLA",
            line_number=200
        )
        violation = LinterRuleEngine.check_transformation_persona_consistency(
            mismatch_node, spatial=self.spatial
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "RULE_8_ANATOMICAL_PERSONA_MISMATCH")

    def test_rule8_stella_big_tiddy_steve_persona_valid(self):
        self.spatial.set_character_stage("STELLA", AnatomicalStage.STELLA_BIG_TIDDY_STEVE)

        valid_node = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="Ouch! Ouch! Stop poking me with the curtain rod! I have delicate nerd ribs now! Ouch!",
            speaker="BIG TIDDY STEVE",
            line_number=201
        )
        violation = LinterRuleEngine.check_transformation_persona_consistency(
            valid_node, spatial=self.spatial
        )
        self.assertIsNone(violation, "Valid Big Tiddy Steve dialogue must pass Rule 8")

    def test_rule8_hayley_bbl_influencer_persona_mismatch(self):
        self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_BBL_INFLUENCER)

        mismatch_node = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I am an investigative reporter writing a major exposé on corporate health rackets!",
            speaker="INFLUENCER BBL HAYLEY",
            line_number=300
        )
        violation = LinterRuleEngine.check_transformation_persona_consistency(
            mismatch_node, spatial=self.spatial
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "RULE_8_ANATOMICAL_PERSONA_MISMATCH")

    def test_rule8_hayley_bbl_influencer_persona_valid(self):
        self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_BBL_INFLUENCER)

        valid_node = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I have to do bumping stuff with beautiful girls and butts and creamy tender thighs... Bye now!",
            speaker="INFLUENCER BBL HAYLEY",
            line_number=301
        )
        violation = LinterRuleEngine.check_transformation_persona_consistency(
            valid_node, spatial=self.spatial
        )
        self.assertIsNone(violation, "Valid Influencer BBL Hayley dialogue must pass Rule 8")


class TestFullChronologyWithMilestone2(unittest.TestCase):
    def test_master_chronology_passes_with_m2_rules(self):
        chronology_path = Path(__file__).resolve().parent.parent.parent / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        script_text = chronology_path.read_text(encoding="utf-8")
        ast = FountainParser.parse(script_text)

        manifest_path = Path(__file__).resolve().parent.parent / "config" / "hot_scoomp_manifest.json"
        from narrative_composer.cli import load_manifest
        epistemic, spatial, _ = load_manifest(str(manifest_path))

        linter = ScreenplayLinter(epistemic, spatial)
        violations = linter.lint_full_script(ast)

        self.assertEqual(
            len(violations),
            0,
            f"Expected zero violations with M1 + M2 active, got {len(violations)}: {[v.diagnostic_message for v in violations[:5]]}"
        )


if __name__ == "__main__":
    unittest.main()
