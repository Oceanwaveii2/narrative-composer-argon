"""Tests for the review-first prose conditioning pass."""

import tempfile
import unittest
from pathlib import Path

from narrative_composer.condition import (
    apply_proposals,
    plan_conditioning,
    run_conditioning,
    load_reviewed_proposals,
)

SCRIPT = """INT. HALL - DAY

The plan was simple. It would work.

**DANA:** "Ready."
"""


class FakeProvider:
    model_name = "fake"

    def __init__(self, suffix: str = " The floor ticked."):
        self.suffix = suffix

    def generate_rewrite(self, request, prompt):  # noqa: ARG002
        return request.original_text + self.suffix


class RejectingProvider:
    model_name = "reject"

    def generate_rewrite(self, request, prompt):  # noqa: ARG002
        return ""


class QuotingProvider:
    model_name = "quoting"

    def generate_rewrite(self, request, prompt):  # noqa: ARG002
        return '"' + request.original_text + " The floor ticked." + '"'


class LengthRetryProvider:
    model_name = 'length-retry'

    def __init__(self):
        self.prompts = []
        self.originals = []

    def generate_rewrite(self, request, prompt):
        self.prompts.append(prompt)
        self.originals.append(request.original_text)
        if len(self.prompts) == 1:
            return request.original_text + ' Extra words.' * 20
        return request.original_text + ' The floor ticked.'


class ReversalRetryProvider:
    model_name = 'reversal-retry'

    def __init__(self):
        self.prompts = []

    def generate_rewrite(self, request, prompt):
        self.prompts.append(prompt)
        return ('Dana leaves the door. She waits for Alex.' if len(self.prompts) == 1 else
                'Dana stays beside the cold door. She waits for Alex.')


class TestConditioning(unittest.TestCase):
    def test_explicit_action_target_can_be_conditioned_without_automatic_warning(self):
        from narrative_composer.compiler.document import parse_document, BlockRole
        text = 'INT. ROOM - DAY\n\nThe lamp hummed in the dark room.\n'
        document = parse_document(text)
        block = next(b for b in document.blocks if b.role == BlockRole.ACTION)
        self.assertEqual(plan_conditioning(text, FakeProvider()), [])
        selected = plan_conditioning(text, FakeProvider(), document=document, target_block_ids=[block.id])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].block_id, block.id)
        self.assertEqual(selected[0].warnings, [])
        self.assertFalse(selected[0].reviewed)

    def test_conditioner_holds_a_rewrite_that_drops_the_possessed_key(self):
        from narrative_composer.compiler.document import parse_document, BlockRole
        text = 'INT. HALL - DAY\n\nDana locks the door. Alex stays inside with the key.\n'
        document = parse_document(text)
        block = next(b for b in document.blocks if b.role == BlockRole.ACTION)
        class OmissionProvider:
            def generate_rewrite(self, request, prompt):
                return "Dana's turn of the lock clicks. Alex waits behind the door."
        proposal = plan_conditioning(text, OmissionProvider(), document=document,
                                     target_block_ids=[block.id])[0]
        self.assertFalse(proposal.accepted)
        self.assertIn('Possible omitted possessed key', proposal.reason)
        self.assertFalse(proposal.reviewed)

    def test_conditioner_retries_an_omitted_key_without_accepting_first_attempt(self):
        from narrative_composer.compiler.document import parse_document, BlockRole
        text = 'INT. HALL - DAY\n\nDana locks the door. Alex stays inside with the key.\n'
        document = parse_document(text)
        block = next(b for b in document.blocks if b.role == BlockRole.ACTION)
        class RetryProvider:
            def __init__(self): self.calls = 0
            def generate_rewrite(self, request, prompt):
                self.calls += 1
                return ("Dana locks the door. Alex waits inside." if self.calls == 1 else
                        "Dana locks the door. Alex stays inside, key in hand.")
        provider = RetryProvider()
        proposal = plan_conditioning(text, provider, document=document, target_block_ids=[block.id])[0]
        self.assertEqual(provider.calls, 2)
        self.assertTrue(proposal.accepted, proposal.reason)
        self.assertIn('Possible omitted possessed key', proposal.attempt_reasons[0])
        self.assertFalse(proposal.reviewed)

    def test_flags_and_accepts_a_sensory_deficit_span(self):
        proposals = plan_conditioning(SCRIPT, FakeProvider())
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertTrue(proposal.accepted, proposal.reason)
        self.assertIn("Sensory deficit", "; ".join(proposal.warnings))
        self.assertNotEqual(proposal.proposed, proposal.original)

    def test_apply_changes_only_the_target_line(self):
        proposals = plan_conditioning(SCRIPT, FakeProvider())
        updated, applied = apply_proposals(SCRIPT, proposals, approved_ids=[p.block_id for p in proposals])

        self.assertEqual(applied, 1)
        before = SCRIPT.split("\n")
        after = updated.split("\n")
        self.assertEqual(len(before), len(after))
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertIn("The floor ticked.", after[changed[0]])
        self.assertIn('**DANA:**', updated)

    def test_rejects_empty_candidates(self):
        proposals = plan_conditioning(SCRIPT, RejectingProvider())
        self.assertEqual(len(proposals), 1)
        self.assertFalse(proposals[0].accepted)
        self.assertIn("empty", proposals[0].reason)

    def test_rejects_oversized_rewrites(self):
        proposals = plan_conditioning(SCRIPT, FakeProvider(suffix=" " + "word " * 80))
        self.assertFalse(proposals[0].accepted)
        self.assertIn("length ratio", proposals[0].reason)
        self.assertEqual(len(proposals[0].attempt_reasons), 2)

    def test_length_retry_uses_original_and_keeps_the_same_gate(self):
        provider = LengthRetryProvider()
        proposals = plan_conditioning(SCRIPT, provider, limit=1)
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertTrue(proposal.accepted, proposal.reason)
        self.assertEqual(provider.originals, [proposal.original, proposal.original])
        self.assertEqual(len(provider.prompts), 2)
        self.assertIn('characters', provider.prompts[0])
        self.assertIn('REVISION CORRECTION', provider.prompts[1])
        self.assertIn('length ratio', proposal.attempt_reasons[0])
        self.assertEqual(proposal.attempt_reasons[1], 'ok')
        self.assertFalse(proposal.reviewed)

    def test_article_change_is_not_mistaken_for_a_missing_name(self):
        from narrative_composer.condition import _lost_subject
        self.assertFalse(_lost_subject('The glass rested on a shelf.', 'A glass rested on a shelf.'))
        self.assertTrue(_lost_subject('Dana opens the door.', 'Alex opens the door.'))
        self.assertFalse(_lost_subject('Dana opens the door.', 'DANA opens the door.'))
        self.assertFalse(_lost_subject('Dana stands beside Alex. Together, they sit.',
                                       'Dana and Alex sit together.'))
        self.assertTrue(_lost_subject('Dana stands beside Alex. Together, they sit.',
                                      'Dana sits down.'))

    def test_chinese_group_subject_is_not_silently_dropped(self):
        from narrative_composer.prose.models import ProseRewriteRequest, SpanCategory
        from narrative_composer.prose.validation import validate_rewrite
        request = ProseRewriteRequest(request_id='test', project_id='test', document_id='test',
            base_revision=1, target_span_id='sample', original_text='第二行：大家一起检查计划。安全校对。',
            category=SpanCategory.STAGE_ACTION)
        _, violations, _ = validate_rewrite('检查计划。安全校对。', request)
        self.assertIn('Possible dropped group subject; author review required', violations)
        _, preserved, _ = validate_rewrite('第二行：众人一同检查计划，安全校对。', request)
        self.assertNotIn('Possible dropped group subject; author review required', preserved)

    def test_reversal_is_retried_without_accepting_the_reversal(self):
        provider = ReversalRetryProvider()
        text = 'Dana stays beside the door. She waits for Alex.\n'
        proposal = plan_conditioning(text, provider, limit=1)[0]
        self.assertTrue(proposal.accepted, proposal.reason)
        self.assertIn('Possible reversed action', proposal.attempt_reasons[0])
        self.assertIn('subject, and object owner unchanged', provider.prompts[1])
        self.assertIn('stays', proposal.proposed)
        self.assertEqual(apply_proposals(text, [proposal]), (text, 0))

    def test_scoped_conditioning_sends_only_the_selected_action(self):
        from narrative_composer.compiler.document import BlockRole, parse_document
        text = 'The plan was simple. It would work.\n\nThe glass was still. It sat on the shelf.\n'
        blocks = [block for block in parse_document(text).blocks if block.role == BlockRole.ACTION]
        provider = LengthRetryProvider()
        proposals = plan_conditioning(text, provider, limit=1, target_block_ids=[blocks[1].id])
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].block_id, blocks[1].id)
        self.assertTrue(all(item == blocks[1].text for item in provider.originals))
        with self.assertRaises(ValueError):
            plan_conditioning(text, provider, target_block_ids=['missing'])

    def test_strips_stray_wrapping_quotes(self):
        proposals = plan_conditioning(SCRIPT, QuotingProvider())
        self.assertTrue(proposals[0].accepted, proposals[0].reason)
        self.assertFalse(proposals[0].proposed.startswith('"'))
        self.assertFalse(proposals[0].proposed.endswith('"'))
        self.assertIn("The floor ticked.", proposals[0].proposed)

    def test_run_conditioning_writes_review_and_conditioned_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "story.md"
            source.write_text(SCRIPT, encoding="utf-8")
            out = Path(tmp) / "conditioned"

            preview = Path(tmp) / 'preview'
            run_conditioning(source, preview, title='Test Story', provider=FakeProvider())
            reviewed = load_reviewed_proposals(preview/'proposals.json')
            result = run_conditioning(source, out, apply=True, title="Test Story", provider=RejectingProvider(),
                approved_ids=[p.block_id for p in reviewed], reviewed_proposals=reviewed)

            self.assertEqual(result["flagged"], 1)
            self.assertEqual(result["applied"], 1)
            self.assertTrue((out / "proposals.json").exists())
            self.assertTrue((out / "review.html").exists())
            self.assertTrue((out / "story.conditioned.md").exists())
            self.assertTrue((out / "reader.conditioned.html").exists())

            conditioned = (out / "story.conditioned.md").read_text(encoding="utf-8")
            self.assertIn("The floor ticked.", conditioned)
            self.assertIn('**DANA:**', conditioned)

    def test_conditioning_never_regenerates_approved_text_or_overwrites_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'story.md'; source.write_bytes(SCRIPT.replace('\n','\r\n').encode())
            preview=Path(tmp)/'preview'
            run_conditioning(source,preview,provider=FakeProvider())
            reviewed=load_reviewed_proposals(preview/'proposals.json')
            ids=[p.block_id for p in reviewed]
            with self.assertRaises(ValueError):
                run_conditioning(source,Path(tmp)/'unsafe',apply=True,approved_ids=ids,provider=FakeProvider())
            with self.assertRaises(FileExistsError):
                run_conditioning(source,preview,provider=FakeProvider())
            result=run_conditioning(source,Path(tmp)/'accepted',apply=True,approved_ids=ids,
                                    reviewed_proposals=reviewed,provider=RejectingProvider())
            output=Path(result['artifacts']['conditioned']).read_bytes()
            self.assertNotIn(b'\r\r\n',output)
            self.assertEqual(source.read_bytes(),SCRIPT.replace('\n','\r\n').encode())
            self.assertIn(b'The floor ticked.',output)


if __name__ == "__main__":
    unittest.main()
