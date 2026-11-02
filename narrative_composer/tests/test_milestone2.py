"""
Milestone 2 Test Suite: Fountain AST Parser & Screenplay Invariant Linter.
Runs via standard library unittest.
"""

import unittest
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.models.ast_nodes import ASTNodeType
from narrative_composer.models.epistemic import (
    EpistemicMatrix,
    NarrativeFact,
    FactCategory,
    EpistemicBelief,
)
from narrative_composer.models.spatial_fsm import (
    SpatialGraph,
    PhysicalEntity,
    ItemLifecycle,
    BodySlot,
)
from narrative_composer.linter.screenplay_linter import ScreenplayLinter


class TestFountainParser(unittest.TestCase):
    def test_standard_fountain_parsing(self):
        script = """
INT. SMITH HOUSE - LIVING ROOM - NIGHT

Storm light strobes through the windows.

HAYLEY
(scratching)
It's under my skin, Holly!

HOLLY
Breathe through the tingle.
"""
        ast = FountainParser.parse(script)
        self.assertEqual(len(ast), 7)
        self.assertEqual(ast[0].node_type, ASTNodeType.SCENE_HEADING)
        self.assertEqual(ast[0].content, "INT. SMITH HOUSE - LIVING ROOM - NIGHT")

        self.assertEqual(ast[1].node_type, ASTNodeType.ACTION)
        self.assertIn("Storm light", ast[1].content)

        self.assertEqual(ast[2].node_type, ASTNodeType.CHARACTER)
        self.assertEqual(ast[2].speaker, "HAYLEY")

        self.assertEqual(ast[3].node_type, ASTNodeType.PARENTHETICAL)
        self.assertEqual(ast[3].content, "(scratching)")

        self.assertEqual(ast[4].node_type, ASTNodeType.DIALOGUE)
        self.assertEqual(ast[4].content, "It's under my skin, Holly!")

        self.assertEqual(ast[5].node_type, ASTNodeType.CHARACTER)
        self.assertEqual(ast[5].speaker, "HOLLY")

        self.assertEqual(ast[6].node_type, ASTNodeType.DIALOGUE)
        self.assertEqual(ast[6].content, "Breathe through the tingle.")

    def test_markdown_cue_parsing(self):
        script = """
### `INT. SMITH HOUSE - LIVING ROOM - NIGHT`

*Hayley freezes. The scratching stops dead.*

**STELLA:** *(smug)* "I have no idea what you're talking about."

**HAYLEY FITNESS GODDESS (CONT'D):** "This isn't funny!"
"""
        ast = FountainParser.parse(script)
        # Heading, Action, Character (Stella), Paren, Dialogue, Character (Hayley), Dialogue
        self.assertEqual(ast[0].node_type, ASTNodeType.SCENE_HEADING)
        self.assertEqual(ast[0].content, "INT. SMITH HOUSE - LIVING ROOM - NIGHT")

        self.assertEqual(ast[1].node_type, ASTNodeType.ACTION)
        self.assertEqual(ast[1].content, "Hayley freezes. The scratching stops dead.")

        # Stella Cue
        self.assertEqual(ast[2].node_type, ASTNodeType.CHARACTER)
        self.assertEqual(ast[2].speaker, "STELLA")

        self.assertEqual(ast[3].node_type, ASTNodeType.PARENTHETICAL)
        self.assertEqual(ast[3].content, "(smug)")

        self.assertEqual(ast[4].node_type, ASTNodeType.DIALOGUE)
        self.assertEqual(ast[4].content, "I have no idea what you're talking about.")

        # Hayley Cue (CONT'D stripped from speaker)
        self.assertEqual(ast[5].node_type, ASTNodeType.CHARACTER)
        self.assertEqual(ast[5].speaker, "HAYLEY FITNESS GODDESS")

        self.assertEqual(ast[6].node_type, ASTNodeType.DIALOGUE)
        self.assertEqual(ast[6].content, "This isn't funny!")


class TestScreenplayLinter(unittest.TestCase):
    def setUp(self):
        # Epistemic Setup
        self.epistemic = EpistemicMatrix()
        self.epistemic.facts["fact_steve"] = NarrativeFact(
            fact_id="fact_steve",
            category=FactCategory.IDENTITY,
            canonical_text="Steve identity reveal",
            embargo_tokens=["Steve", "Steven"]
        )
        self.epistemic.set_belief("STELLA", "fact_steve", EpistemicBelief.UNKNOWN)
        self.epistemic.set_belief("FRANCINE", "fact_steve", EpistemicBelief.KNOWN_TRUE)

        # Spatial Setup
        self.spatial = SpatialGraph(
            character_locations={
                "STELLA": "living_room",
                "HAYLEY": "living_room",
                "FRANCINE": "outside"
            },
            items={
                "gloria_lamp": PhysicalEntity(
                    item_id="gloria_lamp",
                    name="Gloria the Flamingo Lamp",
                    lifecycle=ItemLifecycle.DESTROYED,
                    room_id="living_room"
                ),
                "stella_polo_buttons": PhysicalEntity(
                    item_id="stella_polo_buttons",
                    name="Stella's Polo Buttons",
                    lifecycle=ItemLifecycle.EXPENDED,
                    room_id="living_room",
                    held_by="STELLA",
                    charges_remaining=0
                )
            }
        )
        self.linter = ScreenplayLinter(self.epistemic, self.spatial)

    def test_rule1_token_embargo_violation(self):
        script = """
**STELLA:** "Steve would hate this!"
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_1_FORBIDDEN_TOKEN_EMBARGO")
        self.assertIn("steve", violations[0].diagnostic_message.lower())

    def test_rule1_allowed_when_fact_known(self):
        # Francine is moved into living_room so Rule 5 does not fire
        self.spatial.move_character("FRANCINE", "living_room")
        script = """
**FRANCINE:** "You look like a Steve."
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        # Francine knows fact_steve and is in room, so no violation
        self.assertEqual(len(violations), 0)

    def test_rule2a_zombie_lamp_destruction(self):
        script = """
*Hayley's butt swings wide and Gloria the Flamingo Lamp shatters across the floor.*
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_2A_ZOMBIE_PROP_DESTRUCTION")

    def test_rule2b_button_overdepletion(self):
        script = """
*Her yellow polo buttons pop off and ping against the TV.*
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_2B_PROP_OVER_DEPLETION")

    def test_rule3_phantom_citation(self):
        script = """
**HAYLEY:** "You called my blog 'fresh old protein powder' on Twitter!"
"""
        ast = FountainParser.parse(script)
        prior_committed = "STELLA: You look silly in tie-dye."
        violations = self.linter.lint_beat(ast, active_room_id="living_room", prior_committed_script=prior_committed)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_3_PHANTOM_DIALOGUE_CITATION")
        self.assertIn("fresh old protein powder", violations[0].diagnostic_message)

    def test_rule3_passes_when_citation_exists(self):
        script = """
**HAYLEY:** "You called my blog 'fresh old protein powder' on Twitter!"
"""
        ast = FountainParser.parse(script)
        prior_committed = "STELLA: Her blog is pure fresh old protein powder."
        violations = self.linter.lint_beat(ast, active_room_id="living_room", prior_committed_script=prior_committed)
        self.assertEqual(len(violations), 0)

    def test_rule4_double_discovery(self):
        # Move Francine into living_room so Rule 5 does not fire
        self.spatial.move_character("FRANCINE", "living_room")
        script = """
**FRANCINE:** "Are those rocket ships?"
"""
        ast = FountainParser.parse(script)
        discovered = {"rocket_ships"}
        violations = self.linter.lint_beat(ast, active_room_id="living_room", discovered_features=discovered)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_4_DOUBLE_DISCOVERY")

    def test_rule5_speaker_absent_from_room(self):
        # Francine is located in 'outside'
        script = """
**FRANCINE:** "What's all that noise in there?"
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, "RULE_5_SPEAKER_ABSENT_FROM_ROOM")

    def test_clean_beat_passes_with_zero_violations(self):
        script = """
**STELLA:** "This tie-dye outfit is ridiculous!"

**HAYLEY:** "I'm a fitness mogul now, sis!"
"""
        ast = FountainParser.parse(script)
        violations = self.linter.lint_beat(ast, active_room_id="living_room")
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()
