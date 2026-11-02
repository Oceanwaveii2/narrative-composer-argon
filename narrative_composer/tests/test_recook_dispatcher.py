"""
Milestone 4 Test Suite: Dual-Tier Recook & Surgical Patch Dispatcher.
Validates:
1. DispatchRuleClassifier: Correct routing to Tier 1 (Surgical) vs Tier 2 (Prose Recook).
2. SurgicalPatcher: Deterministic repair of trademarks, parentheticals, and debris hazards.
3. ProseRecooker: Neural conditioning through style profiles.
4. RecookDispatcher: Full orchestration, audit trail generation, and RevisionLedger logging.
5. End-to-end integration and convergence testing.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.linter.rules import LintViolation
from narrative_composer.prose.ledger import RevisionLedger
from narrative_composer.compiler.recook_dispatcher import (
    RecookDispatcher,
    SurgicalPatcher,
    ProseRecooker,
    DispatchRuleClassifier,
    DispatchTier,
)
from narrative_composer.cli import cmd_recook


class TestDispatchClassifier(unittest.TestCase):
    def test_tier_1_surgical_classification(self):
        v_trademark = LintViolation(
            rule_id="RULE_9_SOURCE_NAME_EMBARGO",
            line_number=10,
            offending_text="prep the Kardashian stabilizer",
            diagnostic_message="Leaked trademark",
            repair_instruction="Replace token"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_trademark), DispatchTier.TIER_1_SURGICAL)

        v_parenthetical = LintViolation(
            rule_id="RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL",
            line_number=15,
            offending_text="(whining in Roger's high-pitched cadence)",
            diagnostic_message="Meta parenthetical",
            repair_instruction="Replace with delivery cue"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_parenthetical), DispatchTier.TIER_1_SURGICAL)

        v_debris = LintViolation(
            rule_id="RULE_7_DEBRIS_HAZARD_SAFETY",
            line_number=20,
            offending_text="Francine walks barefoot across the floor",
            diagnostic_message="Barefoot near shards",
            repair_instruction="Step carefully"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_debris), DispatchTier.TIER_1_SURGICAL)

        v_amnesia = LintViolation(
            rule_id="RULE_13_COGNITIVE_SATURATION_LEAK",
            line_number=25,
            offending_text="I must stay faithful to my husband Jeff",
            diagnostic_message="Lucid recall while suppressed",
            repair_instruction="Reflect amnesia"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_amnesia), DispatchTier.TIER_1_SURGICAL)

    def test_tier_2_prose_rewrite_classification(self):
        v_persona = LintViolation(
            rule_id="RULE_8_ANATOMICAL_PERSONA_MISMATCH",
            line_number=30,
            offending_text="I am way too cool for this cheer squad",
            diagnostic_message="Persona mismatch",
            repair_instruction="Rewrite into Steve persona"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_persona), DispatchTier.TIER_2_PROSE_REWRITE)

        v_exposition = LintViolation(
            rule_id="RULE_11_EXPOSITION_BUDGET_WARNING",
            line_number=35,
            offending_text="As you know, my entire backstory began in 1982 when I...",
            diagnostic_message="Exposition budget exceeded",
            repair_instruction="Break up monologue"
        )
        self.assertEqual(DispatchRuleClassifier.classify(v_exposition), DispatchTier.TIER_2_PROSE_REWRITE)


class TestSurgicalPatcher(unittest.TestCase):
    def test_patch_trademark_leak(self):
        script = 'HOLLY: "Lock her up while we prep the Kardashian stabilizer and Kardashian blend."'
        v = LintViolation(
            rule_id="RULE_9_SOURCE_NAME_EMBARGO",
            line_number=1,
            offending_text="prep the Kardashian stabilizer",
            diagnostic_message="Trademark leak",
            repair_instruction="Replace token"
        )
        patched_script, record = SurgicalPatcher.patch_violation(v, script)
        self.assertIsNotNone(record)
        self.assertIn("Calabasas stabilizer", patched_script)
        self.assertNotIn("Kardashian stabilizer", patched_script)

    def test_patch_parenthetical_shorthand(self):
        script = 'HAYLEY\n(whining in Roger\'s high-pitched cadence)\n"This place is a dump!"'
        v = LintViolation(
            rule_id="RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL",
            line_number=2,
            offending_text="(whining in Roger's high-pitched cadence)",
            diagnostic_message="Director shorthand",
            repair_instruction="Replace shorthand"
        )
        patched_script, record = SurgicalPatcher.patch_violation(v, script)
        self.assertIsNotNone(record)
        self.assertIn("(shrill, petulant whine)", patched_script)
        self.assertNotIn("cadence", patched_script)

    def test_patch_debris_hazard_safety(self):
        script = "Francine walks barefoot across the living room carpet."
        v = LintViolation(
            rule_id="RULE_7_DEBRIS_HAZARD_SAFETY",
            line_number=1,
            offending_text="Francine walks barefoot across the living room carpet.",
            diagnostic_message="Debris hazard",
            repair_instruction="Acknowledge shards"
        )
        patched_script, record = SurgicalPatcher.patch_violation(v, script)
        self.assertIsNotNone(record)
        self.assertIn("tiptoeing carefully over the ceramic shards", patched_script)

    def test_cognitive_rule_does_not_invent_amnesia(self):
        script = 'HAYLEY\n"I must remain faithful to my husband Jeff!"'
        v = LintViolation(
            rule_id="RULE_13_COGNITIVE_SATURATION_LEAK",
            line_number=2,
            offending_text='"I must remain faithful to my husband Jeff!"',
            diagnostic_message="Lucid recall while suppressed",
            repair_instruction="Reflect amnesic confusion"
        )
        patched_script, record = SurgicalPatcher.patch_violation(v, script)
        self.assertIsNone(record)
        self.assertEqual(patched_script, script)


class TestRecookDispatcherOrchestration(unittest.TestCase):
    def setUp(self):
        self.ledger = RevisionLedger()
        self.dispatcher = RecookDispatcher(ledger=self.ledger, provider_type="mock")

    def test_end_to_end_dispatch_and_ledger_recording(self):
        script = (
            '### `INT. HG CONGO COMPOUND - LOCKER ROOM - NIGHT`\n\n'
            'HOLLY\n"Lock her in the room while we prep the Kardashian stabilizer."\n\n'
            'HAYLEY\n(whining in Roger\'s high-pitched cadence)\n"My glutes weigh more than a Civic!"\n'
        )

        violations = [
            LintViolation(
                rule_id="RULE_9_SOURCE_NAME_EMBARGO",
                line_number=4,
                offending_text="prep the Kardashian stabilizer",
                diagnostic_message="Trademark leak",
                repair_instruction="Replace token"
            ),
            LintViolation(
                rule_id="RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL",
                line_number=7,
                offending_text="(whining in Roger's high-pitched cadence)",
                diagnostic_message="Director shorthand",
                repair_instruction="Replace shorthand"
            ),
        ]

        report = self.dispatcher.dispatch_all(script, violations)
        self.assertEqual(report.total_violations_evaluated, 2)
        self.assertEqual(report.tier1_patches_applied, 0)
        self.assertFalse(report.is_fully_resolved, "Patch counts cannot establish freshly checked resolution")
        self.assertEqual(report.reconstructed_script, script)
        self.assertEqual(len(report.pending_proposals), 2)
        self.assertTrue(all(p['decision']=='pending author review' for p in report.pending_proposals))

        # Confirm transactions logged to RevisionLedger
        rev = self.ledger.get_current_revision("hot_scoomp", "master_screenplay")
        self.assertEqual(rev, 0)

    def test_duplicate_text_proposal_keeps_the_target_line(self):
        script = 'Kardashian stabilizer\nKardashian stabilizer\n'
        violation = LintViolation(rule_id='RULE_9_SOURCE_NAME_EMBARGO',line_number=2,
            offending_text='Kardashian stabilizer',diagnostic_message='source name',repair_instruction='review')
        report = self.dispatcher.dispatch_all(script,[violation])
        self.assertEqual(report.reconstructed_script,script)
        self.assertEqual(report.pending_proposals[0]['line'],2)
        self.assertEqual(report.pending_proposals[0]['original'],'Kardashian stabilizer')

    def test_cli_recook_preserves_crlf_source_and_refuses_overwrite(self):
        from narrative_composer.models.epistemic import EpistemicMatrix
        from narrative_composer.models.spatial_fsm import SpatialGraph
        violation = LintViolation(rule_id='RULE_9_SOURCE_NAME_EMBARGO',line_number=2,
            offending_text='Kardashian stabilizer',diagnostic_message='source name',repair_instruction='review')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'story.md'
            original = b'Heading\r\nKardashian stabilizer\r\n'
            source.write_bytes(original)
            with patch('narrative_composer.cli.load_manifest',return_value=(EpistemicMatrix(),SpatialGraph(),None)), \
                 patch('narrative_composer.cli.ScreenplayLinter.lint_full_script',return_value=[violation]):
                report = cmd_recook('ignored',str(source))
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(len(report.pending_proposals),1)
                with self.assertRaises(ValueError): cmd_recook('ignored',str(source),out_path=str(source))
                self.assertEqual(source.read_bytes(),original)


if __name__ == "__main__":
    unittest.main()
