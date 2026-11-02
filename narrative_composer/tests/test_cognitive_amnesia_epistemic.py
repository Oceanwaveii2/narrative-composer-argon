"""
Milestone 3 Test Suite: Cognitive Overload & Amnesic Epistemic Matrix (Theory of Mind).
Validates:
1. COGNITIVE_SUPPRESSION and AMNESIA_BLANK state transitions.
2. Embargo token enforcement during cognitive suppression.
3. Rule 13: Proactive recall violation while overloaded.
4. Rule 13: Lucid affirmation violation when prompted about suppressed domestic facts.
5. Rule 13: Valid amnesic blankness ("What's a Jeff?!") passing.
6. Full chronology continuity across all 13 rules.
"""

from pathlib import Path
import unittest

from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.epistemic import (
    EpistemicMatrix,
    EpistemicBelief,
    FactCategory,
    NarrativeFact,
)
from narrative_composer.models.spatial_fsm import SpatialGraph
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.linter.rules import LinterRuleEngine


class TestCognitiveAmnesiaEpistemicMatrix(unittest.TestCase):
    def setUp(self):
        self.epistemic = EpistemicMatrix()
        self.fact_jeff = NarrativeFact(
            fact_id="fact_husband_jeff",
            category=FactCategory.DOMESTIC_RELATION,
            ground_truth=True,
            canonical_text="Hayley is married to Jeff Fischer.",
            embargo_tokens=["husband jeff", "my husband", "married to jeff", "jeff fischer"]
        )
        self.epistemic.facts[self.fact_jeff.fact_id] = self.fact_jeff
        self.epistemic.set_belief("HAYLEY", "fact_husband_jeff", EpistemicBelief.KNOWN_TRUE)

    def test_suppression_and_amnesia_state_transitions(self):
        self.assertEqual(self.epistemic.get_belief("HAYLEY", "fact_husband_jeff"), EpistemicBelief.KNOWN_TRUE)
        self.assertFalse(self.epistemic.is_fact_suppressed("HAYLEY", "fact_husband_jeff"))

        # Transition into cognitive suppression
        self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])
        self.assertEqual(self.epistemic.get_belief("HAYLEY", "fact_husband_jeff"), EpistemicBelief.COGNITIVE_SUPPRESSION)
        self.assertTrue(self.epistemic.is_fact_suppressed("HAYLEY", "fact_husband_jeff"))

        # Embargo tokens are now active for Hayley
        embargoes = self.epistemic.get_embargoed_tokens_for_character("HAYLEY")
        self.assertIn("my husband", embargoes)
        self.assertIn("jeff fischer", embargoes)

        # Transition into complete amnesic blank
        self.epistemic.trigger_amnesic_blank("HAYLEY", "fact_husband_jeff")
        self.assertEqual(self.epistemic.get_belief("HAYLEY", "fact_husband_jeff"), EpistemicBelief.AMNESIA_BLANK)
        self.assertTrue(self.epistemic.is_fact_suppressed("HAYLEY", "fact_husband_jeff"))

    def test_rule13_proactive_recall_violation(self):
        self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])

        dialogue_node = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I must return home to my husband before nightfall.",
            speaker="HAYLEY",
            line_number=150
        )
        violation = LinterRuleEngine.check_cognitive_saturation_amnesia(
            dialogue_node, epistemic=self.epistemic, prior_committed_script=""
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "RULE_13_COGNITIVE_SATURATION_LEAK")
        self.assertIn("proactively recalled 'my husband'", violation.diagnostic_message)

    def test_rule13_lucid_affirmation_when_prompted_violation(self):
        self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])

        prior_script = 'FRANCINE: "Hayley! What about your husband, Jeff?! Are you cheating on Jeff Fischer?!"'

        lucid_dialogue = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="I love my husband Jeff and I will honor my marriage vows!",
            speaker="HAYLEY",
            line_number=155
        )
        violation = LinterRuleEngine.check_cognitive_saturation_amnesia(
            lucid_dialogue, epistemic=self.epistemic, prior_committed_script=prior_script
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "RULE_13_COGNITIVE_SATURATION_LEAK")
        self.assertIn("gave a lucid response instead of exhibiting amnesic disorientation", violation.diagnostic_message)

    def test_rule13_amnesic_blank_response_passes(self):
        self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])

        prior_script = 'FRANCINE: "Hayley! What about your husband, Jeff?! Isn\'t running off with your aerobics coach technically infidelity?!"'

        amnesic_dialogue = ASTElement(
            node_type=ASTNodeType.DIALOGUE,
            content="Je...ff? What? Who? What is a Jeff?!",
            speaker="INFLUENCER BBL HAYLEY",
            line_number=160
        )
        violation = LinterRuleEngine.check_cognitive_saturation_amnesia(
            amnesic_dialogue, epistemic=self.epistemic, prior_committed_script=prior_script
        )
        self.assertIsNone(violation, "Valid amnesic confusion response must pass Rule 13")


class TestFullChronologyWithMilestone3(unittest.TestCase):
    def test_master_chronology_passes_with_m1_m2_m3_rules(self):
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
            f"Expected zero violations with M1 + M2 + M3 active, got {len(violations)}: {[v.diagnostic_message for v in violations[:5]]}"
        )


if __name__ == "__main__":
    unittest.main()
