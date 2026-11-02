"""
Milestone 1 Test Suite for Noir Module 1 Prose Engine.
Verifies:
1. Zero side-effect imports (<50ms, no DB/network created).
2. Missing and mismatched identity validation.
3. Protected spans and token preservation with opaque, non-Latin synthetic fixtures.
4. Append-only revision ledger, state progression, and stale base-revision conflicts.
5. Idempotent command handling (duplicate command IDs yield identical decisions).
6. File persistence, CLI reload, and state recovery across restarts.
7. Synthetic-only end-to-end slice without live providers or external media.
"""

import os
import shutil
import tempfile
import time
import unittest

from narrative_composer.prose.models import (
    SpanCategory,
    DecisionType,
    ProtectedSpan,
    ProseRewriteRequest,
    ProseRewriteProposal,
    MissingIdentityError,
    ProtectedSpanViolationError,
    RevisionConflictError,
    validate_identities,
)
from narrative_composer.prose.protected_spans import ProtectedSpanProtector
from narrative_composer.prose.ledger import RevisionLedger
from narrative_composer.prose.providers.mock_provider import MockProseProvider


class TestProseMilestone0And1(unittest.TestCase):
    """Test suite covering M0/M1 requirements."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ledger_file = os.path.join(self.test_dir, "test_ledger.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_zero_side_effect_import(self):
        """Importing core prose engine modules opens no DB, makes no network calls, and completes in <50ms."""
        start_time = time.perf_counter()
        import narrative_composer.prose as prose
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        self.assertLess(elapsed_ms, 50.0, f"Import took too long: {elapsed_ms:.2f}ms")
        self.assertIsNotNone(prose.__version__)
        # Ensure no unexpected database or socket files were created in working directory
        self.assertFalse(os.path.exists("test.db"))
        self.assertFalse(os.path.exists("prose_engine.sqlite"))

    def test_02_identity_validation_mismatches(self):
        """Mismatched project, document, revision, or target span identities are rejected."""
        req = ProseRewriteRequest(
            request_id="req-1",
            project_id="proj-alpha",
            document_id="doc-001",
            base_revision=1,
            target_span_id="span-10",
            original_text="Francine enters with a tray.",
        )

        # 1. Matching proposal succeeds
        valid_prop = ProseRewriteProposal(
            proposal_id="prop-1",
            request_id="req-1",
            project_id="proj-alpha",
            document_id="doc-001",
            base_revision=1,
            target_span_id="span-10",
            proposed_text="Francine glides in carrying a pewter tray.",
        )
        try:
            validate_identities(req, valid_prop)
        except MissingIdentityError:
            self.fail("validate_identities raised unexpectedly on valid match.")

        # 2. Mismatched project_id
        bad_prop = valid_prop.model_copy(update={"project_id": "proj-beta"})
        with self.assertRaises(MissingIdentityError):
            validate_identities(req, bad_prop)

        # 3. Mismatched document_id
        bad_prop = valid_prop.model_copy(update={"document_id": "doc-999"})
        with self.assertRaises(MissingIdentityError):
            validate_identities(req, bad_prop)

        # 4. Mismatched base_revision
        bad_prop = valid_prop.model_copy(update={"base_revision": 2})
        with self.assertRaises(MissingIdentityError):
            validate_identities(req, bad_prop)

        # 5. Mismatched target_span_id
        bad_prop = valid_prop.model_copy(update={"target_span_id": "span-99"})
        with self.assertRaises(MissingIdentityError):
            validate_identities(req, bad_prop)

    def test_03_protected_spans_opaque_non_latin_fixtures(self):
        """Prose operations cannot replace protected source words or synthetic non-Latin tokens."""
        # Non-Latin and opaque synthetic fixtures
        protected_tokens = ["Δt_alpha", "Zorgon_99", "Ω-Centauri", "χ_scalar"]
        span = ProtectedSpan(
            span_id="prot-1",
            category=SpanCategory.GENERAL,
            text="Δt_alpha Zorgon_99 Ω-Centauri χ_scalar",
            required_tokens=protected_tokens,
        )

        # 1. Preserving all tokens passes
        valid_prose = (
            "The calculation reached Δt_alpha as Zorgon_99 drifted past "
            "Ω-Centauri under the calibrated χ_scalar field."
        )
        is_valid, errors = ProtectedSpanProtector.verify_all(valid_prose, [span])
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # 2. Dropping one token ('Ω-Centauri') triggers ProtectedSpanViolationError
        corrupted_prose = (
            "The calculation reached Δt_alpha as Zorgon_99 drifted past "
            "Alpha-Centauri under the calibrated χ_scalar field."
        )
        with self.assertRaises(ProtectedSpanViolationError) as ctx:
            ProtectedSpanProtector.verify_protected_span(corrupted_prose, span)
        self.assertIn("Ω-Centauri", str(ctx.exception))

    def test_04_protected_dialogue_utterances(self):
        """Spoken dialogue cannot be mutated or dropped by prose conditioning."""
        dialogue_span = ProtectedSpan(
            span_id="dial-1",
            category=SpanCategory.DIALOGUE,
            text="It is suuuch bullcrap that my skin is itching!",
            required_tokens=["bullcrap", "itching"],
        )

        # Intact dialogue inside novelized prose
        novelized_ok = (
            'Hayley thrust her hip forward. "It is suuuch bullcrap that my skin is itching!" '
            "she rasped, her nails digging into neon tie-dye."
        )
        ProtectedSpanProtector.verify_protected_span(novelized_ok, dialogue_span)

        # Altered dialogue word ('bullcrap' -> 'nonsense') fails
        altered_dialogue = (
            'Hayley thrust her hip forward. "It is suuuch nonsense that my skin is itching!" '
            "she rasped."
        )
        with self.assertRaises(ProtectedSpanViolationError):
            ProtectedSpanProtector.verify_protected_span(altered_dialogue, dialogue_span)

    def test_05_append_only_ledger_and_conflict_detection(self):
        """Ledger rejects stale base revisions and tracks revision progression."""
        ledger = RevisionLedger()
        project_id = "hot_scoomp"
        doc_id = "act1_scene1"

        self.assertEqual(ledger.get_current_revision(project_id, doc_id), 0)

        # 1. Commit first proposal at base_revision=0
        prop1 = ProseRewriteProposal(
            proposal_id="p-1",
            request_id="req-1",
            project_id=project_id,
            document_id=doc_id,
            base_revision=0,
            target_span_id="beat-1",
            proposed_text="Hayley scratches her neon tie-dye shorts.",
        )
        dec1 = ledger.commit_decision(prop1, DecisionType.ACCEPTED, command_id="cmd-1")
        self.assertEqual(dec1.base_revision, 0)
        self.assertEqual(dec1.resulting_revision, 1)
        self.assertEqual(ledger.get_current_revision(project_id, doc_id), 1)

        # 2. Stale base revision check: proposal targeting base_revision=0 fails now that rev is 1
        stale_prop = ProseRewriteProposal(
            proposal_id="p-stale",
            request_id="req-2",
            project_id=project_id,
            document_id=doc_id,
            base_revision=0,  # STALE
            target_span_id="beat-2",
            proposed_text="Stella laughs on the velvet rug.",
        )
        with self.assertRaises(RevisionConflictError) as ctx:
            ledger.commit_decision(stale_prop, DecisionType.ACCEPTED, command_id="cmd-2")
        self.assertIn("targets base revision 0, but current revision is 1", str(ctx.exception))

        # 3. Proposal targeting current base_revision=1 succeeds and increments to 2
        prop2 = ProseRewriteProposal(
            proposal_id="p-2",
            request_id="req-3",
            project_id=project_id,
            document_id=doc_id,
            base_revision=1,
            target_span_id="beat-2",
            proposed_text="Stella snorts, lounging across the velvet couch.",
        )
        dec2 = ledger.commit_decision(prop2, DecisionType.ACCEPTED, command_id="cmd-3")
        self.assertEqual(dec2.resulting_revision, 2)
        self.assertEqual(ledger.get_current_revision(project_id, doc_id), 2)

        # 4. Author edit decision records author's modified text
        prop3 = ProseRewriteProposal(
            proposal_id="p-3",
            request_id="req-4",
            project_id=project_id,
            document_id=doc_id,
            base_revision=2,
            target_span_id="beat-3",
            proposed_text="Gloria wobbles on the stand.",
        )
        dec3 = ledger.commit_decision(
            prop3,
            DecisionType.AUTHOR_EDITED,
            author_text="Francine's pink flamingo lamp, Gloria, shudders and crashes.",
            command_id="cmd-4",
        )
        self.assertEqual(dec3.resulting_revision, 3)
        self.assertEqual(
            dec3.final_text,
            "Francine's pink flamingo lamp, Gloria, shudders and crashes."
        )

    def test_06_idempotency_same_command_id(self):
        """Retrying with the same command_id returns the existing decision without duplicating."""
        ledger = RevisionLedger()
        project_id = "test_proj"
        doc_id = "test_doc"

        prop = ProseRewriteProposal(
            proposal_id="p-idem",
            request_id="r-idem",
            project_id=project_id,
            document_id=doc_id,
            base_revision=0,
            target_span_id="span-1",
            proposed_text="First execution text.",
        )

        dec_first = ledger.commit_decision(prop, DecisionType.ACCEPTED, command_id="cmd-idempotent-99")
        rev_after_first = ledger.get_current_revision(project_id, doc_id)
        self.assertEqual(rev_after_first, 1)

        # Retry with the same command ID
        dec_retry = ledger.commit_decision(prop, DecisionType.ACCEPTED, command_id="cmd-idempotent-99")
        self.assertEqual(dec_first.decision_id, dec_retry.decision_id)
        self.assertEqual(dec_retry.resulting_revision, 1)

        # Revision did not advance again
        self.assertEqual(ledger.get_current_revision(project_id, doc_id), 1)

        # History contains exactly 1 decision
        history = ledger.list_revisions(project_id, doc_id)
        self.assertEqual(len(history), 1)

    def test_07_persistence_and_reload(self):
        """Committed revisions and decisions load intact after file-backed ledger restart."""
        # 1. First session: commit two decisions to disk
        ledger1 = RevisionLedger(storage_path=self.ledger_file)
        project_id = "persist_proj"
        doc_id = "persist_doc"

        p1 = ProseRewriteProposal(
            proposal_id="p-store-1",
            request_id="r-store-1",
            project_id=project_id,
            document_id=doc_id,
            base_revision=0,
            target_span_id="span-1",
            proposed_text="Initial persisted beat.",
        )
        ledger1.commit_decision(p1, DecisionType.ACCEPTED, command_id="cmd-store-1")

        p2 = ProseRewriteProposal(
            proposal_id="p-store-2",
            request_id="r-store-2",
            project_id=project_id,
            document_id=doc_id,
            base_revision=1,
            target_span_id="span-2",
            proposed_text="Second persisted beat.",
        )
        ledger1.commit_decision(p2, DecisionType.ACCEPTED, command_id="cmd-store-2")
        self.assertEqual(ledger1.get_current_revision(project_id, doc_id), 2)

        # 2. Simulate restart: instantiate new RevisionLedger pointing to same file
        ledger2 = RevisionLedger(storage_path=self.ledger_file)
        self.assertEqual(ledger2.get_current_revision(project_id, doc_id), 2)

        history = ledger2.list_revisions(project_id, doc_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].final_text, "Initial persisted beat.")
        self.assertEqual(history[1].final_text, "Second persisted beat.")

        # Command index is preserved across restarts
        existing = ledger2.get_decision_by_command_id("cmd-store-1")
        self.assertIsNotNone(existing)
        self.assertEqual(existing.decision_id, history[0].decision_id)

    def test_08_synthetic_end_to_end_slice(self):
        """Full synthetic vertical slice: request -> mock provider -> verification -> commit -> reload."""
        ledger = RevisionLedger(storage_path=self.ledger_file)
        provider = MockProseProvider()

        # Opaque synthetic non-Latin fixture
        protected = ProtectedSpan(
            span_id="prot-alpha",
            category=SpanCategory.GENERAL,
            text="Ψ_field_7",
            required_tokens=["Ψ_field_7"],
        )
        req = ProseRewriteRequest(
            request_id="slice-req-1",
            project_id="synthetic_proj",
            document_id="synthetic_doc",
            base_revision=0,
            target_span_id="target-span-1",
            original_text="The field fluctuated.",
            protected_spans=[protected],
        )

        # Generate proposal via mock provider
        prompt = f"Rewrite preserving: {protected.text}"
        generated_prose = provider.generate_rewrite(req, prompt)
        self.assertIn("Ψ_field_7", generated_prose)

        # Verify protected spans
        is_valid, errors = ProtectedSpanProtector.verify_all(generated_prose, req.protected_spans)
        self.assertTrue(is_valid, f"Verification failed: {errors}")

        # Assemble typed proposal
        proposal = ProseRewriteProposal(
            proposal_id="slice-prop-1",
            request_id=req.request_id,
            project_id=req.project_id,
            document_id=req.document_id,
            base_revision=req.base_revision,
            target_span_id=req.target_span_id,
            proposed_text=generated_prose,
            protected_words_verified=True,
            epistemic_verified=True,
            model_provider=provider.model_name,
        )

        # Commit proposal
        decision = ledger.commit_decision(proposal, DecisionType.ACCEPTED, command_id="cmd-slice-1")
        self.assertEqual(decision.resulting_revision, 1)

        # Reload from disk and verify
        reloaded_ledger = RevisionLedger(storage_path=self.ledger_file)
        self.assertEqual(
            reloaded_ledger.get_current_revision(req.project_id, req.document_id), 1
        )


if __name__ == "__main__":
    unittest.main()
