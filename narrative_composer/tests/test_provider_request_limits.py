"""Request caps are enforced before transport; all responses are local fakes."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.providers.codex_session import CodexSessionProseProvider
from narrative_composer.prose.providers.deepseek import DeepSeekProseProvider
from narrative_composer.prose.providers.venice import VeniceProseProvider
from narrative_composer.prose.providers.gemini_flash import (
    ProviderConfigurationError, ProviderExecutionError,
)


def response(finish="stop"):
    return SimpleNamespace(status_code=200, json=lambda: {
        "choices": [{"finish_reason": finish, "message": {"content": "Dana waits by the door."}}],
    })


class ProviderRequestLimitTests(unittest.TestCase):
    def setUp(self):
        self.request = ProseRewriteRequest(
            request_id="request-limits", project_id="test", document_id="test",
            base_revision=1, target_span_id="span", original_text="Dana waits.",
        )

    def test_deepseek_default_and_explicit_output_caps_reach_payload(self):
        for kwargs, expected in (({}, 4096), ({"max_output_tokens": 256}, 256)):
            with self.subTest(expected=expected):
                provider = DeepSeekProseProvider(api_key="test-only", **kwargs)
                with patch("httpx.post", return_value=response()) as send:
                    provider.generate_rewrite(self.request, "Repair this paragraph.")
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.kwargs["json"]["max_tokens"], expected)

    def test_venice_generation_and_rewrite_have_explicit_output_cap(self):
        provider = VeniceProseProvider(api_key="test-only", max_output_tokens=256)
        with patch("httpx.post", return_value=response()) as send:
            provider.generate_text("Draft one paragraph.")
            provider.generate_rewrite(self.request, "Repair one paragraph.")
        self.assertEqual(send.call_count, 2)
        for call in send.call_args_list:
            self.assertEqual(call.kwargs["json"]["max_completion_tokens"], 256)

    def test_oversized_multibyte_deepseek_input_is_rejected_before_transport(self):
        provider = DeepSeekProseProvider(api_key="test-only", max_input_bytes=1024)
        with patch("httpx.post") as send:
            with self.assertRaisesRegex(ProviderConfigurationError, "UTF-8 bytes"):
                provider.chat([{"role": "user", "content": "é" * 600}])
        send.assert_not_called()

    def test_both_venice_paths_reject_oversized_input_before_transport(self):
        provider = VeniceProseProvider(api_key="test-only", max_input_bytes=1024)
        for rewrite in (False, True):
            with self.subTest(rewrite=rewrite), patch("httpx.post") as send:
                with self.assertRaisesRegex(ProviderConfigurationError, "UTF-8 bytes"):
                    if rewrite:
                        provider.generate_rewrite(self.request, "é" * 600)
                    else:
                        provider.generate_text("é" * 600)
                send.assert_not_called()

    def test_invalid_api_limits_cannot_disable_bounds(self):
        invalid = (None, False, True, 0, -1, float("inf"), float("nan"), "4096")
        for cls in (DeepSeekProseProvider, VeniceProseProvider):
            for value in invalid:
                for field in ("max_input_bytes", "max_output_tokens"):
                    with self.subTest(provider=cls.__name__, field=field, value=repr(value)):
                        with self.assertRaises(ProviderConfigurationError):
                            cls(api_key="test-only", **{field: value})
            with self.assertRaises(ProviderConfigurationError):
                cls(api_key="test-only", max_output_tokens=32769)
            with self.assertRaises(ProviderConfigurationError):
                cls(api_key="test-only", max_input_bytes=262145)

    def test_incomplete_output_is_rejected_once_without_expanding_budget(self):
        for cls in (DeepSeekProseProvider, VeniceProseProvider):
            with self.subTest(provider=cls.__name__):
                provider = cls(api_key="test-only")
                with patch("httpx.post", return_value=response("length")) as send:
                    with self.assertRaises(ProviderExecutionError):
                        provider.generate_rewrite(self.request, "Repair one paragraph.")
                self.assertEqual(send.call_count, 1)

    def test_truncation_stops_batch_before_another_paragraph_is_submitted(self):
        from narrative_composer.condition import plan_conditioning
        text = ("INT. HALL - DAY\n\nThe plan was simple. It would work.\n\n"
                "The next plan was simple. It would work.\n")
        for cls in (DeepSeekProseProvider, VeniceProseProvider):
            with self.subTest(provider=cls.__name__):
                provider = cls(api_key="test-only")
                with patch("httpx.post", return_value=response("length")) as send:
                    proposals = plan_conditioning(text, provider, limit=2)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(len(proposals), 1)
                self.assertFalse(proposals[0].accepted)
                self.assertIn("finish: length", proposals[0].reason)

    def test_codex_limit_includes_instructions_and_rejects_before_runner(self):
        runner = Mock(side_effect=AssertionError("Codex must not run"))
        provider = CodexSessionProseProvider(
            executable="codex", runner=runner, max_input_bytes=1024,
        )
        with self.assertRaisesRegex(ProviderConfigurationError, "UTF-8 bytes"):
            provider.generate_rewrite(self.request, "x" * 1000)
        runner.assert_not_called()
        self.assertEqual(provider.model_name, "gpt-6.1-terra")
        self.assertEqual(provider.reasoning_effort, "max")

    def test_codex_invalid_input_budget_is_rejected(self):
        for value in (0, True, float("inf"), None, 262145):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ProviderConfigurationError):
                    CodexSessionProseProvider(max_input_bytes=value)


if __name__ == "__main__":
    unittest.main()
