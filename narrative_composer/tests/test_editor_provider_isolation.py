"""Automated proposals use independent requests; explicit chat keeps its session."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch, sentinel

from narrative_composer.editor import EditorHandler
from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.providers.codex_session import CodexSessionProseProvider
from narrative_composer.prose.providers.deepseek import DeepSeekProseProvider


class EditorProviderIsolationTests(unittest.TestCase):
    def setUp(self):
        self.handler = EditorHandler.__new__(EditorHandler)
        self.handler.server = SimpleNamespace()
        self.request = ProseRewriteRequest(
            request_id="isolation", project_id="test", document_id="test",
            base_revision=1, target_span_id="span", original_text="Dana waits.",
        )

    def test_automated_providers_never_open_chat_sessions(self):
        with patch.object(self.handler, "_codex_session", side_effect=AssertionError("Chat used")), \
             patch.object(self.handler, "_deepseek_session", side_effect=AssertionError("Chat used")), \
             patch("narrative_composer.prose.providers.deepseek.load_deepseek_api_key", return_value="test-only"):
            codex = self.handler._provider("codex")
            deepseek = self.handler._provider("deepseek")
        self.assertIsInstance(codex, CodexSessionProseProvider)
        self.assertEqual(codex.model_name, "gpt-6.1-terra")
        self.assertEqual(codex.reasoning_effort, "max")
        self.assertIsInstance(deepseek, DeepSeekProseProvider)
        self.assertFalse(hasattr(self.handler.server, "codex_session"))
        self.assertFalse(hasattr(self.handler.server, "deepseek_sessions"))

    def test_second_deepseek_proposal_does_not_replay_first(self):
        response = SimpleNamespace(status_code=200, json=lambda: {
            "choices": [{"finish_reason": "stop", "message": {"content": "Dana waits."}}],
        })
        with patch.object(self.handler, "_deepseek_session", side_effect=AssertionError("Chat used")), \
             patch("narrative_composer.prose.providers.deepseek.load_deepseek_api_key", return_value="test-only"), \
             patch("httpx.post", return_value=response) as send:
            provider = self.handler._provider("deepseek")
            provider.generate_rewrite(self.request, "Repair paragraph one.")
            provider.generate_rewrite(self.request, "Repair paragraph two.")
        self.assertEqual(send.call_count, 2)
        for call, prompt in zip(send.call_args_list, ("Repair paragraph one.", "Repair paragraph two.")):
            messages = call.kwargs["json"]["messages"]
            self.assertEqual([m["role"] for m in messages], ["system", "user"])
            self.assertEqual(messages[1]["content"], prompt)

    def test_explicit_chat_keeps_persistent_sessions(self):
        with patch.object(self.handler, "_codex_session", return_value=sentinel.codex_chat) as codex, \
             patch.object(self.handler, "_deepseek_session", return_value=sentinel.deepseek_chat) as deepseek:
            self.assertIs(self.handler._writing_session("codex"), sentinel.codex_chat)
            self.assertIs(self.handler._writing_session("deepseek"), sentinel.deepseek_chat)
        codex.assert_called_once_with()
        deepseek.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
