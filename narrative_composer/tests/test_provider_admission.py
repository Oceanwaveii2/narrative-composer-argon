"""One live proposal job per editor; ordinary editing remains available."""
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from narrative_composer.editor import guard_identical_provider_request, provider_work_without_commit_lock
from narrative_composer.persistence import COMMIT_LOCK, WorkspaceConflict


class ProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.server = SimpleNamespace(default_provider="deepseek")
        self.source = Path("fixture-story.md")
        self.first = {"provider": "deepseek", "target_block_ids": ["first"], "request_id": "a" * 32}

    def guard(self, payload, route="/api/condition"):
        return guard_identical_provider_request(self.server, route, self.source, payload)

    def test_distinct_live_jobs_are_rejected(self):
        cases = [
            ("/api/condition", {"provider": "deepseek", "target_block_ids": ["second"]}),
            ("/api/condition", {"provider": "codex", "target_block_ids": ["first"]}),
            ("/api/compose", {"provider": "venice"}),
            ("/api/recook", {}),
        ]
        with COMMIT_LOCK:
            with self.guard(self.first):
                original = set(self.server.inflight_provider_requests)
                for route, payload in cases:
                    with self.subTest(route=route, payload=payload):
                        with self.assertRaisesRegex(WorkspaceConflict, "Another provider proposal"):
                            with self.guard(payload, route):
                                self.fail("Second live job admitted")
                        self.assertEqual(self.server.inflight_provider_requests, original)
        self.assertFalse(self.server.inflight_provider_requests)

    def test_request_id_cannot_bypass_duplicate_guard(self):
        expected = ("This same proposal request is already running; "
                    "check its result and history before retrying")
        with COMMIT_LOCK:
            with self.guard(self.first):
                for request_id in ("a" * 32, "b" * 32):
                    with self.assertRaises(WorkspaceConflict) as caught:
                        with self.guard(dict(self.first, request_id=request_id)):
                            self.fail("Duplicate admitted")
                    self.assertEqual(str(caught.exception), expected)

    def test_exception_releases_job_slot(self):
        with COMMIT_LOCK:
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                with self.guard(self.first):
                    raise RuntimeError("simulated")
            self.assertFalse(self.server.inflight_provider_requests)
            with self.guard({"provider": "codex"}):
                self.assertEqual(len(self.server.inflight_provider_requests), 1)
        self.assertFalse(self.server.inflight_provider_requests)

    def test_mock_work_is_local_and_does_not_remove_live_reservation(self):
        with COMMIT_LOCK:
            with self.guard(self.first):
                original = set(self.server.inflight_provider_requests)
                with self.guard({"provider": "mock"}):
                    self.assertEqual(len(self.server.inflight_provider_requests), 2)
                self.assertEqual(self.server.inflight_provider_requests, original)
            with self.guard({"provider": "mock"}):
                with self.assertRaisesRegex(WorkspaceConflict, "Another provider proposal"):
                    with self.guard({}):
                        self.fail("Live job admitted during existing work")

    def test_ordinary_editor_work_can_acquire_commit_lock(self):
        acquired = threading.Event()
        observed = []
        def ordinary_work():
            with COMMIT_LOCK:
                observed.append(len(self.server.inflight_provider_requests))
                acquired.set()
        worker = threading.Thread(target=ordinary_work, daemon=True)
        with COMMIT_LOCK:
            with self.guard(self.first), provider_work_without_commit_lock():
                worker.start()
                available = acquired.wait(2)
        worker.join(2)
        self.assertTrue(available)
        self.assertFalse(worker.is_alive())
        self.assertEqual(observed, [1])
        self.assertFalse(self.server.inflight_provider_requests)


if __name__ == "__main__":
    unittest.main()
