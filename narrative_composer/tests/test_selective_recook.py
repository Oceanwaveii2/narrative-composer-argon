"""Tests for selective, review-first re-cook."""

import unittest
from pathlib import Path

from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.selective_recook import apply_patch, apply_patches, plan_patches

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "hot_scoomp_manifest.json"

CLEAN = '''INT. OFFICE - DAY

A lamp glows on the desk.

**DANA:** "Hello there."
'''

DIRTY_SOURCE_NAME = '''INT. OFFICE - DAY

The Hot Scoomp poster hangs crooked.

**DANA:** "Nice place."
'''

DIRTY_PARENTHETICAL = '''INT. OFFICE - DAY

STELLA
(full Kardashian cadence)
"I refuse."

'''

TELEPATHIC = '''INT. OFFICE - DAY

**HAYLEY:** "Jello shots for everyone!"

**STELLA:** "I want jello shots too."
'''


class TestSelectiveRecook(unittest.TestCase):
    def test_clean_text_plans_nothing(self):
        self.assertEqual(plan_patches(CLEAN, MANIFEST), [])

    def test_plans_a_surgical_patch_for_a_source_name(self):
        patches = plan_patches(DIRTY_SOURCE_NAME, MANIFEST)
        self.assertTrue(patches, "expected a patch for the embargoed source name")
        patch = patches[0]
        self.assertEqual(patch.rule_id, "RULE_9_SOURCE_NAME_EMBARGO")
        self.assertEqual(patch.tier, "tier_1_surgical")
        self.assertIn("Hot Scoomp", patch.original)
        self.assertNotIn("Hot Scoomp", patch.proposed)
        self.assertTrue(patch.block_id.startswith("action-"))

    def test_plans_a_parenthetical_rewrite(self):
        patches = plan_patches(DIRTY_PARENTHETICAL, MANIFEST)
        self.assertTrue(patches)
        self.assertIn(patches[0].rule_id, {"RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL", "RULE_9_SOURCE_NAME_EMBARGO"})
        self.assertTrue(patches[0].block_id.startswith("parenthetical-"))

    def test_plans_a_neural_patch_for_telepathy(self):
        patches = plan_patches(TELEPATHIC, MANIFEST)
        self.assertEqual(patches, [], "The oversized placeholder mock must fail the rewrite gate")

    def test_apply_patch_changes_only_that_line(self):
        patches = plan_patches(DIRTY_SOURCE_NAME, MANIFEST)
        patch = patches[0]
        updated = apply_patch(DIRTY_SOURCE_NAME, patch)

        before = DIRTY_SOURCE_NAME.split("\n")
        after = updated.split("\n")
        self.assertEqual(len(before), len(after))
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(changed), 1, "exactly one source line may change")
        self.assertEqual(after[patch.line - 1], changed and after[patch.line - 1])
        self.assertIn(patch.proposed, after[patch.line - 1])

    def test_apply_patches_preserves_document_shape(self):
        patches = plan_patches(TELEPATHIC, MANIFEST)
        updated = apply_patches(TELEPATHIC, patches)
        self.assertEqual(
            len(parse_document(updated).blocks), len(parse_document(TELEPATHIC).blocks)
        )


if __name__ == "__main__":
    unittest.main()
