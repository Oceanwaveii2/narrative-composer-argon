"""
Regression tests for the second-priority (P1) defects fixed after the audit.

Covers:
  1. Transformation pills must match whole cue tokens, never substrings.
  2. The lexer must survive a UTF-8 BOM and markdown '##' scene headings.
  3. Inline stage parentheticals must become their own PARENTHETICAL node.
  4. Discovery must not turn shouted sentence fragments into characters.
"""

import unittest
from pathlib import Path

from narrative_composer.compiler.html_compiler import get_character_transformation_pill
from narrative_composer.graph.discover import discover
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry
from narrative_composer.linter.rules import LinterRuleEngine
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.models.ast_nodes import ASTNodeType

ROOT = Path(__file__).resolve().parents[2]


class TestP1Regressions(unittest.TestCase):
    def test_pill_matching_is_token_bounded(self):
        # Substrings of a cue must never trigger a transformation pill.
        for name in ("BOB", "DEBORAH", "NOBODY", "STEVEN", "MA MA LING"):
            self.assertIsNone(get_character_transformation_pill(name), f"{name} must not get a pill")
        # Real transformation cues still do.
        for name in ("BIG TIDDY STEVE", "STEVE", "RAINEE/MADONNA", "NURSE FRANCINE"):
            self.assertIsNotNone(get_character_transformation_pill(name), f"{name} must get a pill")

    def test_parser_strips_bom_and_accepts_hash_headings(self):
        bom_heading = "\ufeff### `INT. ROOM - DAY`\n\nA lamp.\n"
        ast = FountainParser.parse(bom_heading)
        self.assertEqual(ast[0].node_type, ASTNodeType.SCENE_HEADING)
        self.assertNotIn("\ufeff", ast[0].content)

        hash_heading = "## INT. ROOM - DAY\n\nA lamp.\n"
        ast_hash = FountainParser.parse(hash_heading)
        self.assertEqual(ast_hash[0].node_type, ASTNodeType.SCENE_HEADING)

    def test_inline_parenthetical_is_split_from_dialogue(self):
        script = "INT. ROOM - DAY\n\nSTELLA\n(quietly) \"Hello.\"\n"
        ast = FountainParser.parse(script)
        types = [e.node_type for e in ast]
        self.assertIn(ASTNodeType.PARENTHETICAL, types)
        paren = next(e for e in ast if e.node_type == ASTNodeType.PARENTHETICAL)
        dialogue = next(e for e in ast if e.node_type == ASTNodeType.DIALOGUE)
        self.assertEqual(paren.content, "(quietly)")
        self.assertNotIn("quietly", dialogue.content)
        self.assertEqual(dialogue.content, "Hello.")

    def test_discovery_ignores_shouted_fragments(self):
        script = (
            "EXT. DRIVEWAY - DAY\n"
            "Cheese EVERYWHERE. Some of it on the bar.\n"
        )
        ast = FountainParser.parse(script)
        graph = StoryGraph.from_registry(load_registry(include_auto=False))
        res = discover(ast, graph, canon="hot_scoomp_main", run_id="run_noise")
        self.assertNotIn("everywhere", [e["entity_id"] for e in res.new_entities])

    def test_discovery_keeps_real_introductions(self):
        script = (
            "EXT. DRIVEWAY - DAY\n"
            "Across the street, STAN SMITH stands by his mailbox.\n"
            "Stan drops the rake.\n"
        )
        ast = FountainParser.parse(script)
        graph = StoryGraph.from_registry(load_registry(include_auto=False))
        res = discover(ast, graph, canon="hot_scoomp_main", run_id="run_stan")
        self.assertIn("stan_smith", [e["entity_id"] for e in res.new_entities])

    def test_rule9_scans_story_text_but_not_document_chrome(self):
        """A source-name embargo is about dialogue/action, not the document's own title."""
        chrome = (
            ASTNodeType.ACT_BANNER,
            ASTNodeType.CHUNK_HEADER,
            ASTNodeType.NOTE,
            ASTNodeType.LEGACY_HEADING,
            ASTNodeType.SCENE_HEADING,
        )
        for node_type in chrome:
            element = ASTElement(
                node_type=node_type, content="HOT SCOOMP: THE KARDASHIAN STABILIZER", line_number=1
            )
            self.assertIsNone(
                LinterRuleEngine.check_source_name_embargo(element),
                f"{node_type.value} is document chrome and must not trip RULE_9",
            )

        for node_type in (ASTNodeType.ACTION, ASTNodeType.DIALOGUE, ASTNodeType.PARENTHETICAL):
            element = ASTElement(
                node_type=node_type, content="This is Hot Scoomp all over again.", line_number=2
            )
            violation = LinterRuleEngine.check_source_name_embargo(element)
            self.assertIsNotNone(violation, f"{node_type.value} is story text and must trip RULE_9")
            self.assertEqual(violation.rule_id, "RULE_9_SOURCE_NAME_EMBARGO")


if __name__ == "__main__":
    unittest.main()
