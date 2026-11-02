"""
Unit tests for Milestone 4: Anti-Exposition Linters & Witness Log.
Tests Rules 9 (Source Embargo), 10 (Telepathic Quoting), 11 (Exposition Warning), and 12 (Director Shorthand).
"""

import unittest
from narrative_composer.linter.rules import LinterRuleEngine, LintViolation
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.spatial_fsm import SpatialGraph


class TestAntiExpositionRules(unittest.TestCase):

    def setUp(self):
        self.spatial = SpatialGraph()
        self.spatial.character_locations = {
            "HAYLEY": "upstairs_bedroom",
            "HOLLY": "upstairs_bedroom",
            "STELLA": "living_room",
        }

    def test_rule_9_source_name_embargo(self):
        # Case 1: Kardashian namedrop
        node_bad_1 = ASTElement(
            line_number=101,
            node_type=ASTNodeType.DIALOGUE,
            speaker="HAYLEY",
            content="Whatever it takes to keep up with the Kardashians, right?",
        )
        v1 = LinterRuleEngine.check_source_name_embargo(node_bad_1)
        self.assertIsNotNone(v1)
        self.assertEqual(v1.rule_id, "RULE_9_SOURCE_NAME_EMBARGO")
        self.assertEqual(v1.severity, "ERROR")

        # Case 2: Boondocks namedrop
        node_bad_2 = ASTElement(
            line_number=102,
            node_type=ASTNodeType.ACTION,
            content="She walks into the room like a character straight out of The Boondocks.",
        )
        v2 = LinterRuleEngine.check_source_name_embargo(node_bad_2)
        self.assertIsNotNone(v2)
        self.assertEqual(v2.rule_id, "RULE_9_SOURCE_NAME_EMBARGO")

        # Case 3: Clean prose with legitimate words
        node_clean = ASTElement(
            line_number=103,
            node_type=ASTNodeType.DIALOGUE,
            speaker="HAYLEY",
            content="This organic bamboo fabric is completely fair trade and sustainable.",
        )
        v_clean = LinterRuleEngine.check_source_name_embargo(node_clean)
        self.assertIsNone(v_clean)

    def test_rule_10_telepathic_phrase_leak(self):
        # Step 1: Hayley speaks "jello shots" in upstairs_bedroom
        self.spatial.record_utterance(
            line_number=10,
            speaker="HAYLEY",
            active_room="upstairs_bedroom",
            text="I'm putting used jello shots in your rear end.",
        )

        # Stella is in living_room, so she did not witness it
        self.assertFalse(self.spatial.was_present_when_spoken("STELLA", "jello shots"))
        self.assertTrue(self.spatial.was_present_when_spoken("HOLLY", "jello shots"))

        # Case 1: Stella telepathically quotes "jello shots"
        node_stella_telepathic = ASTElement(
            line_number=20,
            node_type=ASTNodeType.DIALOGUE,
            speaker="STELLA",
            content="Wait, did someone put jello shots in my body?",
        )
        v_telepathic = LinterRuleEngine.check_telepathic_phrase_leak(node_stella_telepathic, self.spatial)
        self.assertIsNotNone(v_telepathic)
        self.assertEqual(v_telepathic.rule_id, "RULE_10_TELEPATHIC_PHRASE_LEAK")
        self.assertEqual(v_telepathic.severity, "ERROR")

        # Case 2: Holly quotes "jello shots" (Holly was in the bedroom, so it's allowed)
        node_holly_witnessed = ASTElement(
            line_number=21,
            node_type=ASTNodeType.DIALOGUE,
            speaker="HOLLY",
            content="You really did it with jello shots, girl!",
        )
        v_witnessed = LinterRuleEngine.check_telepathic_phrase_leak(node_holly_witnessed, self.spatial)
        self.assertIsNone(v_witnessed)

    def test_rule_11_exposition_budget_warning(self):
        # Case 1: Long uninterrupted exposition monologue (>45 words with marker)
        long_exposition = (
            "Let me explain what happened was that in the previous episode, I went down to the fitness sanctuary "
            "to expose the predatory commercial practices of the wellness gurus who were commodifying women's "
            "bodies through unaccredited aerobics routines and artificial collagen stimulants, which ultimately "
            "led to this catastrophic supernatural genetic transformation that altered my anatomical structure completely."
        )
        node_bad_expo = ASTElement(
            line_number=415,
            node_type=ASTNodeType.DIALOGUE,
            speaker="HAYLEY",
            content=long_exposition,
        )
        v_expo = LinterRuleEngine.check_exposition_budget(node_bad_expo, max_exposition_words=40)
        self.assertIsNotNone(v_expo)
        self.assertEqual(v_expo.rule_id, "RULE_11_EXPOSITION_BUDGET_WARNING")
        self.assertEqual(v_expo.severity, "WARNING")

        # Case 2: Crisp sitcom dialogue (under budget)
        node_clean_expo = ASTElement(
            line_number=416,
            node_type=ASTNodeType.DIALOGUE,
            speaker="HAYLEY",
            content="Let me explain: I went to bust a fitness grift and accidentally became a goddess.",
        )
        v_clean_expo = LinterRuleEngine.check_exposition_budget(node_clean_expo, max_exposition_words=40)
        self.assertIsNone(v_clean_expo)

    def test_rule_12_director_shorthand_parenthetical(self):
        # Case 1: Director shorthand parenthetical
        node_bad_paren = ASTElement(
            line_number=315,
            node_type=ASTNodeType.PARENTHETICAL,
            content="(full Kardashian cadence)",
        )
        v_paren = LinterRuleEngine.check_director_shorthand(node_bad_paren)
        self.assertIsNotNone(v_paren)
        self.assertEqual(v_paren.rule_id, "RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL")
        self.assertEqual(v_paren.severity, "ERROR")

        # Case 2: Homage/style shorthand
        node_bad_paren_2 = ASTElement(
            line_number=316,
            node_type=ASTNodeType.PARENTHETICAL,
            content="(in the style of The Boondocks)",
        )
        v_paren_2 = LinterRuleEngine.check_director_shorthand(node_bad_paren_2)
        self.assertIsNotNone(v_paren_2)
        self.assertEqual(v_paren_2.rule_id, "RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL")

        # Case 3: Valid acting instruction
        node_clean_paren = ASTElement(
            line_number=317,
            node_type=ASTNodeType.PARENTHETICAL,
            content="(deadpan, checking her fingernails)",
        )
        v_clean_paren = LinterRuleEngine.check_director_shorthand(node_clean_paren)
        self.assertIsNone(v_clean_paren)


if __name__ == "__main__":
    unittest.main()
