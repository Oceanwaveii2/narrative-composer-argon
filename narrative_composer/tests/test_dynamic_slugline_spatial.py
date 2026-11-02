"""
Milestone 1 Test Suite: Dynamic Spatial Slugline & Co-Presence Engine.
Validates:
1. Generalized slugline parsing across all setting types, dash conventions, and markdown formats.
2. Canonical room ID generation, hierarchy, and alias mapping.
3. Multi-room co-presence tracking across scene boundaries.
4. (O.S.), (V.O.), (PHONE), (FILTERED) presence exemption gates.
5. Zero Rule 5 false positives on multi-scene master chronologies.
"""

from pathlib import Path
import unittest

from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.spatial_fsm import SpatialGraph, PhysicalEntity, ItemLifecycle
from narrative_composer.models.epistemic import EpistemicMatrix, NarrativeFact, FactCategory
from narrative_composer.parser.slugline_parser import SluglineParser, ParsedSlugline
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.linter.rules import LinterRuleEngine


class TestSluglineParser(unittest.TestCase):
    def test_basic_slugline_parsing(self):
        slug = SluglineParser.parse("INT. LIVING ROOM - DAY")
        self.assertEqual(slug.setting_type, "INT")
        self.assertTrue(slug.is_interior)
        self.assertFalse(slug.is_exterior)
        self.assertEqual(slug.primary_location, "LIVING ROOM")
        self.assertEqual(slug.time_of_day, "DAY")
        self.assertEqual(slug.canonical_room_id, "living_room")

    def test_exterior_slugline_parsing(self):
        slug = SluglineParser.parse("EXT. NEVADA DESERT - DAY")
        self.assertEqual(slug.setting_type, "EXT")
        self.assertFalse(slug.is_interior)
        self.assertTrue(slug.is_exterior)
        self.assertEqual(slug.primary_location, "NEVADA DESERT")
        self.assertEqual(slug.time_of_day, "DAY")
        self.assertEqual(slug.canonical_room_id, "nevada_desert")

    def test_dual_interior_exterior_setting(self):
        slug = SluglineParser.parse("INT/EXT. FOAM-WASH CAR WASH - CONTINUOUS")
        self.assertEqual(slug.setting_type, "INT/EXT")
        self.assertTrue(slug.is_interior)
        self.assertTrue(slug.is_exterior)
        self.assertEqual(slug.primary_location, "FOAM-WASH CAR WASH")
        self.assertEqual(slug.time_of_day, "CONTINUOUS")
        self.assertEqual(slug.canonical_room_id, "foam_wash_car_wash")

    def test_markdown_and_em_dash_slugline(self):
        slug = SluglineParser.parse("### `INT. HG DANCE-CARDIO STUDIO — LOBBY — CONTINUOUS`")
        self.assertEqual(slug.setting_type, "INT")
        self.assertEqual(slug.primary_location, "HG DANCE-CARDIO STUDIO")
        self.assertEqual(slug.secondary_location, "LOBBY")
        self.assertEqual(slug.time_of_day, "CONTINUOUS")
        self.assertEqual(slug.canonical_room_id, "hg_dance_cardio_studio_lobby")
        self.assertEqual(slug.parent_location_id, "hg_dance_cardio_studio")

    def test_compound_domestic_room_with_canonical_short_alias(self):
        slug = SluglineParser.parse("INT. LING-EIDOLESSA HOUSE — LIVING ROOM — DAY")
        self.assertEqual(slug.canonical_room_id, "living_room")
        self.assertEqual(slug.primary_location, "LING-EIDOLESSA HOUSE")
        self.assertEqual(slug.secondary_location, "LIVING ROOM")
        self.assertIn("ling_eidolessa_house_living_room", slug.aliases)
        self.assertIn("ling_eidolessa_house", slug.aliases)

    def test_nightclub_bar_slugline(self):
        slug = SluglineParser.parse("### `INT. THE BUTTON NIGHTCLUB — BAR — CONTINUOUS`")
        self.assertEqual(slug.canonical_room_id, "the_button_nightclub_bar")
        self.assertEqual(slug.parent_location_id, "the_button_nightclub")


class TestSpatialGraphAliasesAndPresence(unittest.TestCase):
    def setUp(self):
        self.spatial = SpatialGraph(
            character_locations={
                "FRANCINE": "the_button_nightclub_bar",
                "HAYLEY": "foam_wash_car_wash",
                "STELLA": "living_room",
            },
            room_aliases={
                "living_room": ["ling_eidolessa_house_living_room", "ling_eidolessa_house"]
            }
        )
        self.epistemic = EpistemicMatrix()

    def test_is_character_in_room_direct_match(self):
        self.assertTrue(self.spatial.is_character_in_room("FRANCINE", "the_button_nightclub_bar"))
        self.assertFalse(self.spatial.is_character_in_room("FRANCINE", "living_room"))

    def test_is_character_in_room_alias_match(self):
        # Stella is in living_room, which aliases ling_eidolessa_house_living_room
        self.assertTrue(self.spatial.is_character_in_room("STELLA", "living_room"))
        self.assertTrue(self.spatial.is_character_in_room("STELLA", "ling_eidolessa_house_living_room"))

    def test_character_normalization(self):
        self.assertEqual(self.spatial.get_character_room("FRANCINE LING"), "the_button_nightclub_bar")
        self.assertEqual(self.spatial.get_character_room("INFLUENCER BBL HAYLEY"), "foam_wash_car_wash")
        self.assertEqual(self.spatial.get_character_room("BIG TIDDY STEVE"), "living_room")

    def test_off_screen_and_voice_over_exemptions(self):
        # Hayley is at the car wash, speaking in the living room
        dialogue_os = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I can hear you over the intercom!",
            speaker="HAYLEY (O.S.)",
            line_number=42
        )
        violation_os = LinterRuleEngine.check_speaker_room_presence(
            dialogue_os, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNone(violation_os, "O.S. dialogue must be exempt from line-of-sight presence")

        dialogue_phone = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="Sell all my assets!",
            speaker="HOLLY (PHONE)",
            line_number=45
        )
        violation_phone = LinterRuleEngine.check_speaker_room_presence(
            dialogue_phone, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNone(violation_phone, "PHONE dialogue must be exempt from line-of-sight presence")

        # On-camera dialogue without O.S. when absent MUST violate Rule 5
        dialogue_on_camera = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I am standing right in front of you!",
            speaker="HAYLEY",
            line_number=50
        )
        violation_on_camera = LinterRuleEngine.check_speaker_room_presence(
            dialogue_on_camera, active_room_id="living_room", spatial=self.spatial
        )
        self.assertIsNotNone(violation_on_camera)
        self.assertEqual(violation_on_camera.rule_id, "RULE_5_SPEAKER_ABSENT_FROM_ROOM")


class TestMultiSceneFullScriptLinter(unittest.TestCase):
    def test_multi_scene_automatic_presence_transition(self):
        script = """
INT. THE BUTTON NIGHTCLUB — BAR — CONTINUOUS

FRANCINE stares at her white wine spritzer with coiled intensity.

FRANCINE
"I cannot believe Stan dumped me at Denny's via GroupMe."

INT. LING-EIDOLESSA HOUSE — LIVING ROOM — DAY

Francine storms into the living room, tossing her clutch on the sofa.

FRANCINE
"Home sweet home."

STELLA
"Who are you talking to?"
"""
        ast = FountainParser.parse(script)
        spatial = SpatialGraph(character_locations={"FRANCINE": "outside", "STELLA": "living_room"})
        epistemic = EpistemicMatrix()
        linter = ScreenplayLinter(epistemic, spatial)

        violations = linter.lint_full_script(ast)
        self.assertEqual(len(violations), 0, f"Expected 0 violations, got: {[v.diagnostic_message for v in violations]}")

    def test_master_chronology_passes_with_zero_violations(self):
        chronology_path = Path(__file__).resolve().parent.parent.parent / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        if not chronology_path.exists():
            self.skipTest("HOT_SCOOMP_COMPLETE_CHRONOLOGY.md not found in root")

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
            f"Expected zero violations on master screenplay, got {len(violations)}: {[v.diagnostic_message for v in violations[:5]]}"
        )


if __name__ == "__main__":
    unittest.main()
