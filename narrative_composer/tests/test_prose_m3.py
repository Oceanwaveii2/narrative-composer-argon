"""
Milestone 3 Test Suite for Noir Module 1 Style Guide, Semantic Drive, and Approved Edits.
Verifies:
1. Show voice profiles and repository lookups.
2. Scoped author-approved edits store with strict profile isolation.
3. Defect-type and keyword-based few-shot retrieval relevance.
4. Semantic drive reference passage indexing and retrieval.
5. End-to-end prompt assembly integrating protected spans, FSM facts, diagnostics, and voice guidelines.
6. Persistence and reload of the approved edits ledger.
"""

import os
import shutil
import tempfile
import unittest

from narrative_composer.prose.approved_edits import ApprovedEditPair, ApprovedEditsStore
from narrative_composer.prose.diagnostics import ProseDiagnosticReport
from narrative_composer.prose.models import (
    ProtectedSpan,
    ProseRewriteRequest,
    SpanCategory,
)
from narrative_composer.prose.prompt_assembler import PromptAssembler
from narrative_composer.prose.semantic_drive import ReferencePassage, SemanticDrive
from narrative_composer.prose.style_engine import (
    HOT_SCOOMP_TV14,
    NOIR_DETECTIVE,
    StyleProfile,
    StyleProfileRepository,
)


class TestProseMilestone3(unittest.TestCase):
    """Test suite covering M3 style guide and scoped retrieval."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.edits_file = os.path.join(self.test_dir, "test_edits.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_style_profile_repository(self):
        """Repository registers, retrieves, and lists built-in show profiles."""
        repo = StyleProfileRepository()
        profiles = repo.list_profiles()
        self.assertIn("hot_scoomp_tv14", profiles)
        self.assertIn("noir_detective", profiles)
        self.assertIn("standard_dramatic", profiles)

        hot_scoomp = repo.get_style_profile("hot_scoomp_tv14")
        self.assertIsNotNone(hot_scoomp)
        self.assertEqual(hot_scoomp.target_psychic_distance, 2)
        self.assertGreaterEqual(hot_scoomp.target_cadence_burstiness, 4.5)
        self.assertTrue(any("ozone" in s for s in hot_scoomp.sensory_preferences))

        # Register custom profile
        custom = StyleProfile(
            profile_id="sci_fi_cyberpunk",
            name="Neon Cyberpunk",
            description="High-tech dystopian street crime.",
        )
        repo.register_profile(custom)
        self.assertEqual(repo.get_style_profile("sci_fi_cyberpunk").name, "Neon Cyberpunk")

    def test_02_approved_edits_strict_profile_isolation(self):
        """Edits from Profile A (Hot Scoomp) never leak into queries for Profile B (Noir)."""
        store = ApprovedEditsStore()

        # Add Hot Scoomp edit
        scoomp_edit = ApprovedEditPair(
            edit_id="edit-scoomp-1",
            profile_id="hot_scoomp_tv14",
            original_text="Hayley noticed her arms were itchy.",
            approved_text="White sparks snapped off Hayley's wrists as her nails dug into neon tie-dye.",
            defect_type="filter_words",
            keywords=["itchy", "arms", "sparks"],
        )
        store.add_edit(scoomp_edit)

        # Add Noir Detective edit
        noir_edit = ApprovedEditPair(
            edit_id="edit-noir-1",
            profile_id="noir_detective",
            original_text="The detective noticed the wet blood on the pavement.",
            approved_text="Rain washed black blood into the curb gutter under the buzzing neon.",
            defect_type="filter_words",
            keywords=["detective", "blood", "pavement"],
        )
        store.add_edit(noir_edit)

        # Query Hot Scoomp: must return scoomp_edit and NEVER noir_edit
        results_scoomp = store.retrieve_relevant_edits(
            profile_id="hot_scoomp_tv14",
            context_text="Hayley scratched her arms vigorously.",
            defect_types=["filter_words"],
        )
        self.assertEqual(len(results_scoomp), 1)
        self.assertEqual(results_scoomp[0].edit_id, "edit-scoomp-1")

        # Query Noir Detective: must return noir_edit and NEVER scoomp_edit
        results_noir = store.retrieve_relevant_edits(
            profile_id="noir_detective",
            context_text="A shadow walked across the pavement.",
            defect_types=["filter_words"],
        )
        self.assertEqual(len(results_noir), 1)
        self.assertEqual(results_noir[0].edit_id, "edit-noir-1")

        # Query an empty/unrelated profile: returns empty list immediately
        results_empty = store.retrieve_relevant_edits(
            profile_id="unrelated_show",
            context_text="Hayley on the pavement.",
            defect_types=["filter_words"],
        )
        self.assertEqual(len(results_empty), 0)

    def test_03_approved_edits_relevance_scoring(self):
        """Retrieval prioritizes matching defect types and keyword overlap."""
        store = ApprovedEditsStore()

        edit_cadence = ApprovedEditPair(
            edit_id="edit-cadence",
            profile_id="hot_scoomp_tv14",
            original_text="Short sentence one. Short sentence two. Short sentence three.",
            approved_text="Sparks flared. Hayley swung wide, the shelf-like tie-dye hips demolishing Mom's plaque in a single shuddering crash.",
            defect_type="monotonous_cadence",
            keywords=["flared", "swung", "plaque"],
        )
        edit_labels = ApprovedEditPair(
            edit_id="edit-labels",
            profile_id="hot_scoomp_tv14",
            original_text="Stop it, Hayley said angrily.",
            approved_text="Hayley bared her teeth, slamming the dumbbell onto the rack.",
            defect_type="label_syntax",
            keywords=["dumbbell", "rack", "teeth"],
        )
        store.add_edit(edit_cadence)
        store.add_edit(edit_labels)

        # Query matching defect_type='label_syntax'
        results = store.retrieve_relevant_edits(
            profile_id="hot_scoomp_tv14",
            context_text="Stella said scornfully to Hayley.",
            defect_types=["label_syntax"],
            max_results=1,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].edit_id, "edit-labels")

    def test_04_semantic_drive_passages(self):
        """Semantic drive indexes reference passages and retrieves them based on scene type."""
        drive = SemanticDrive()

        p1 = ReferencePassage(
            passage_id="ref-prop-1",
            profile_id="hot_scoomp_tv14",
            text="Francine's pink ceramic flamingo lamp, Gloria, teetered precariously on the side table.",
            scene_type="prop_comedy",
            tags=["lamp", "gloria", "fragile"],
        )
        p2 = ReferencePassage(
            passage_id="ref-dialogue-1",
            profile_id="hot_scoomp_tv14",
            text="Stella sprawled across the velvet couch, blowing a bubble of pink gum.",
            scene_type="dialogue_sparring",
            tags=["stella", "couch", "breezy"],
        )
        drive.add_passage(p1)
        drive.add_passage(p2)

        results = drive.retrieve_passages(
            profile_id="hot_scoomp_tv14",
            query_text="Hayley knocked the fragile flamingo lamp.",
            scene_type="prop_comedy",
            max_results=1,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].passage_id, "ref-prop-1")

    def test_05_prompt_assembler_complete_structure(self):
        """Assembles prompt containing inviolable protected spans, FSM facts, diagnostics, and voice guidelines."""
        prot_dialogue = ProtectedSpan(
            span_id="dial-1",
            category=SpanCategory.DIALOGUE,
            text="It is suuuch bullcrap that my skin is itching!",
            required_tokens=["bullcrap", "itching"],
        )
        prot_prop = ProtectedSpan(
            span_id="prop-gloria",
            category=SpanCategory.STAGE_ACTION,
            text="Gloria the flamingo lamp",
            required_tokens=["Gloria", "flamingo", "lamp"],
        )

        req = ProseRewriteRequest(
            request_id="req-m3",
            project_id="hot_scoomp",
            document_id="act1",
            base_revision=0,
            target_span_id="beat-hayley-whirls",
            original_text="Hayley noticed her tie-dye was tight. She felt very upset and said angrily that it hurt.",
            protected_spans=[prot_dialogue, prot_prop],
            active_props={"gloria_lamp": "intact", "yard_of_month_plaque": "hanging"},
            character_epistemic_scope={"Hayley": ["itching_powder_source_unknown", "butt_is_huge"]},
            permitted_facts=["Gloria is currently undamaged on side table."],
            target_psychic_distance=2,
            style_profile_id="hot_scoomp_tv14",
        )

        diag = ProseDiagnosticReport(
            span_id="beat-hayley-whirls",
            filter_word_count=2,
            filter_words_found=["noticed", "felt"],
            label_syntax_detected=True,
            label_examples=["said angrily"],
            sensory_details_count=0,
            burstiness_score=0.5,
            warnings=["Filter words detected: noticed, felt"],
        )

        edits = [
            ApprovedEditPair(
                edit_id="ex-1",
                profile_id="hot_scoomp_tv14",
                original_text="She felt bad.",
                approved_text="She clenched her jaw, fists shaking against her thighs.",
                defect_type="filter_words",
            )
        ]

        prompt = PromptAssembler.assemble(
            request=req,
            diagnostics=diag,
            style_profile=HOT_SCOOMP_TV14,
            approved_edits=edits,
            reference_passages=[],
        )

        # Inviolable checks
        self.assertIn("INVIOLABLE PROTECTED SPANS", prompt)
        self.assertIn("It is suuuch bullcrap that my skin is itching!", prompt)
        self.assertIn("Gloria, flamingo, lamp", prompt)

        # FSM and Epistemic checks
        self.assertIn("gloria_lamp: intact", prompt)
        self.assertIn("itching_powder_source_unknown", prompt)

        # Diagnostic repair instructions
        self.assertIn("ELIMINATE FILTER WORDS (2 found: noticed, felt)", prompt)
        self.assertIn("FIX EMOTION LABELS", prompt)
        self.assertIn("said angrily", prompt)

        # Show voice and few-shot checks
        self.assertIn("American Dad - Hot Scoomp TV-14", prompt)
        self.assertIn("FEW-SHOT APPROVED AUTHOR EXAMPLES", prompt)
        self.assertIn("She clenched her jaw", prompt)

    def test_06_persistence_and_reload_approved_edits(self):
        """ApprovedEditsStore persists and reloads from disk cleanly."""
        store1 = ApprovedEditsStore(storage_path=self.edits_file)
        store1.add_edit(
            ApprovedEditPair(
                edit_id="edit-disk-1",
                profile_id="hot_scoomp_tv14",
                original_text="Draft one text.",
                approved_text="Polished one text.",
                defect_type="general",
            )
        )
        self.assertEqual(store1.count_edits("hot_scoomp_tv14"), 1)

        # Reload in a new store instance
        store2 = ApprovedEditsStore(storage_path=self.edits_file)
        self.assertEqual(store2.count_edits("hot_scoomp_tv14"), 1)
        edits = store2.retrieve_relevant_edits("hot_scoomp_tv14", "Draft one text.")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].approved_text, "Polished one text.")


if __name__ == "__main__":
    unittest.main()
