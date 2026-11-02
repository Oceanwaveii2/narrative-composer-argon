"""Bound conditioning work without contacting a model."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from narrative_composer.condition import (
    load_reviewed_proposals, plan_conditioning, run_conditioning,
)
from narrative_composer.compiler.document import BlockRole, parse_document


class RecordingProvider:
    def __init__(self, *, fail_on_call=None, suffix=" The floor ticked."):
        self.fail_on_call = fail_on_call
        self.suffix = suffix
        self.originals = []

    def generate_rewrite(self, request, prompt):
        self.originals.append(request.original_text)
        if len(self.originals) == self.fail_on_call:
            raise RuntimeError("provider unavailable")
        return request.original_text + self.suffix


class TestConditioningLimits(unittest.TestCase):
    @staticmethod
    def batch_fixture(count=12):
        text = "INT. HALL - DAY\n\n" + "\n\n".join(
            f"The plan for room {index} was simple. It would work."
            for index in range(count)
        ) + "\n"
        document = parse_document(text)
        targets = [block.id for block in document.blocks if block.role == BlockRole.ACTION]
        return text, targets

    def test_default_caps_planner_and_file_runner_at_two_spans(self):
        text, targets = self.batch_fixture(4)
        provider = RecordingProvider()
        proposals = plan_conditioning(text, provider, target_block_ids=targets)
        self.assertEqual(len(provider.originals), 2)
        self.assertEqual([item.block_id for item in proposals], targets[:2])
        self.assertTrue(all(item.accepted for item in proposals))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "story.md"
            source.write_text(text, encoding="utf-8")
            out = Path(tmp) / "conditioned"
            file_provider = RecordingProvider()
            result = run_conditioning(source, out, provider=file_provider)
            self.assertEqual(len(file_provider.originals), 2)
            self.assertEqual(result["flagged"], 2)
            self.assertEqual(len(load_reviewed_proposals(out / "proposals.json")), 2)
            self.assertEqual(source.read_text(encoding="utf-8"), text)

    def test_explicit_one_and_ten_bound_generation(self):
        text, targets = self.batch_fixture(12)
        for limit in (1, 10):
            with self.subTest(limit=limit):
                provider = RecordingProvider()
                proposals = plan_conditioning(text, provider, limit=limit, target_block_ids=targets)
                self.assertEqual(len(provider.originals), limit)
                self.assertEqual([item.block_id for item in proposals], targets[:limit])

    def test_invalid_limits_fail_before_provider_calls_or_construction(self):
        text, targets = self.batch_fixture(4)
        invalid = (None, False, True, 0, -1, 11, 2.0, 2.5,
                   float("inf"), float("-inf"), float("nan"), "2")
        for limit in invalid:
            with self.subTest(limit=repr(limit)):
                provider = RecordingProvider()
                with self.assertRaisesRegex(ValueError, "integer from 1 to 10"):
                    plan_conditioning(text, provider, limit=limit, target_block_ids=targets)
                self.assertEqual(provider.originals, [])
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "story.md"
            source.write_text(text, encoding="utf-8")
            out = Path(tmp) / "conditioned"
            with patch("narrative_composer.condition.create_prose_provider") as factory:
                with self.assertRaisesRegex(ValueError, "integer from 1 to 10"):
                    run_conditioning(source, out, limit=None)
            factory.assert_not_called()
            self.assertFalse(out.exists())

    def test_provider_failure_stops_batch_and_retains_proposals(self):
        text, targets = self.batch_fixture(4)
        for fail_on_call in (1, 2):
            with self.subTest(fail_on_call=fail_on_call):
                provider = RecordingProvider(fail_on_call=fail_on_call)
                proposals = plan_conditioning(text, provider, limit=4, target_block_ids=targets)
                self.assertEqual(len(provider.originals), fail_on_call)
                self.assertEqual(len(proposals), fail_on_call)
                self.assertEqual([item.block_id for item in proposals], targets[:fail_on_call])
                self.assertTrue(all(item.accepted for item in proposals[:-1]))
                self.assertFalse(proposals[-1].accepted)
                self.assertEqual(proposals[-1].proposed, "")
                self.assertIn("provider error: provider unavailable", proposals[-1].reason)
                self.assertTrue(all(item.base_hash for item in proposals))

    def test_failed_batch_saves_previous_proposals(self):
        text, _ = self.batch_fixture(4)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "story.md"
            source.write_text(text, encoding="utf-8")
            out = Path(tmp) / "conditioned"
            provider = RecordingProvider(fail_on_call=2)
            result = run_conditioning(source, out, provider=provider, limit=4)
            saved = load_reviewed_proposals(out / "proposals.json")
            self.assertEqual(len(provider.originals), 2)
            self.assertEqual(result["flagged"], 2)
            self.assertEqual(len(saved), 2)
            self.assertTrue(saved[0].accepted)
            self.assertFalse(saved[1].accepted)
            self.assertIn("provider error:", saved[1].reason)
            self.assertEqual(source.read_text(encoding="utf-8"), text)

    def test_retries_are_bounded_and_retry_failure_stops_batch(self):
        text, targets = self.batch_fixture(4)
        oversized = " " + "word " * 80
        provider = RecordingProvider(suffix=oversized)
        proposals = plan_conditioning(text, provider, target_block_ids=targets)
        self.assertEqual(len(proposals), 2)
        self.assertEqual(len(provider.originals), 4)
        self.assertTrue(all(len(item.attempt_reasons) == 2 for item in proposals))
        self.assertTrue(all(not item.accepted for item in proposals))
        failing = RecordingProvider(fail_on_call=2, suffix=oversized)
        failed = plan_conditioning(text, failing, limit=4, target_block_ids=targets)
        self.assertEqual(len(failing.originals), 2)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].block_id, targets[0])
        self.assertEqual(len(failed[0].attempt_reasons), 2)
        self.assertIn("length ratio", failed[0].attempt_reasons[0])
        self.assertIn("provider error:", failed[0].attempt_reasons[1])
        self.assertFalse(failed[0].accepted)


if __name__ == "__main__":
    unittest.main()
