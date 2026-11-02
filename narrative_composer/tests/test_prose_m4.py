"""
Milestone 4 Test Suite for Noir Module 1 Gemini 3.8 Flash Provider Adapter.
Verifies:
1. Mock provider round-trip and token preservation.
2. Session transport mode with custom handler callback.
3. Configuration validation (missing session handler or missing API key).
4. Error logging and ProviderReceipt auditing.
5. Simulated API transport and HTTP error status handling.
6. Provider factory instantiation.
"""

import unittest
from unittest.mock import MagicMock, patch

from narrative_composer.prose.models import (
    ProtectedSpan,
    ProseRewriteRequest,
    SpanCategory,
)
from narrative_composer.prose.providers import (
    GeminiFlashProseProvider,
    MockProseProvider,
    ProviderConfigurationError,
    ProviderExecutionError,
    TransportMode,
    create_prose_provider,
)


class TestProseMilestone4(unittest.TestCase):
    """Test suite covering M4 model provider adapter and transport modes."""

    def setUp(self):
        self.prot_span = ProtectedSpan(
            span_id="prot-1",
            category=SpanCategory.GENERAL,
            text="Gloria the flamingo lamp",
            required_tokens=["Gloria", "flamingo", "lamp"],
        )
        self.request = ProseRewriteRequest(
            request_id="req-prov-1",
            project_id="hot_scoomp",
            document_id="scene1",
            base_revision=0,
            target_span_id="span-1",
            original_text="The lamp fell.",
            protected_spans=[self.prot_span],
        )

    def test_01_mock_provider_generation_and_receipt(self):
        """Mock provider generates deterministic output containing protected tokens."""
        provider = MockProseProvider(model_name="synthetic-v1")
        output = provider.generate_rewrite(self.request, prompt="Rewrite now")

        self.assertIn("Gloria", output)
        self.assertIn("flamingo", output)
        self.assertIn("lamp", output)
        self.assertEqual(provider.call_count, 1)

    def test_02_gemini_session_transport(self):
        """Session transport routes prompt to injected session callback and records receipt."""
        captured_prompts = []

        def dummy_session(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Gloria the flamingo lamp teetered, pink ceramic trembling against the baseboard."

        provider = GeminiFlashProseProvider(
            transport_mode=TransportMode.SESSION,
            session_handler=dummy_session,
            model_name="gemini-3.8-flash",
        )

        prompt_text = "Assembled prompt packet..."
        output = provider.generate_rewrite(self.request, prompt=prompt_text)

        self.assertEqual(len(captured_prompts), 1)
        self.assertEqual(captured_prompts[0], prompt_text)
        self.assertIn("Gloria the flamingo lamp", output)

        # Receipt checks
        self.assertEqual(len(provider.receipts), 1)
        receipt = provider.receipts[0]
        self.assertEqual(receipt.model_name, "gemini-3.8-flash")
        self.assertEqual(receipt.transport_mode, TransportMode.SESSION)
        self.assertEqual(receipt.status, "success")
        self.assertGreaterEqual(receipt.latency_ms, 0.0)
        self.assertEqual(receipt.raw_response_text, output)

    def test_03_session_transport_missing_handler_error(self):
        """Configuring session mode without a handler raises ProviderConfigurationError."""
        provider = GeminiFlashProseProvider(
            transport_mode=TransportMode.SESSION,
            session_handler=None,
        )
        with self.assertRaises(ProviderConfigurationError) as ctx:
            provider.generate_rewrite(self.request, "prompt")
        self.assertIn("no session_handler callable was provided", str(ctx.exception))

    def test_04_session_transport_execution_error_logged(self):
        """Session handler runtime exceptions are caught, logged in receipts, and wrapped."""
        def failing_session(prompt: str) -> str:
            raise RuntimeError("Underlying session disconnect or timeout")

        provider = GeminiFlashProseProvider(
            transport_mode=TransportMode.SESSION,
            session_handler=failing_session,
        )

        with self.assertRaises(ProviderExecutionError) as ctx:
            provider.generate_rewrite(self.request, "prompt")
        self.assertIn("Session transport error", str(ctx.exception))

        # Check receipt recorded the error
        self.assertEqual(len(provider.receipts), 1)
        self.assertEqual(provider.receipts[0].status, "error")
        self.assertIn("Underlying session disconnect", provider.receipts[0].error_message)

    def test_05_api_transport_missing_key_error(self):
        """Configuring API mode without an API key raises ProviderConfigurationError."""
        with patch.dict("os.environ", {}, clear=True):
            provider = GeminiFlashProseProvider(
                transport_mode=TransportMode.API,
                api_key=None,
            )
            with self.assertRaises(ProviderConfigurationError) as ctx:
                provider.generate_rewrite(self.request, "prompt")
            self.assertIn("no API key was provided", str(ctx.exception))

    def test_06_api_transport_successful_response(self):
        """Simulated Gemini API call parses candidate text and logs telemetry."""
        fake_response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Gloria the flamingo lamp shuddered as the shelf-like tie-dye hips struck."
                            }
                        ]
                    }
                }
            ]
        }

        mock_post = MagicMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = fake_response_data

        with patch("httpx.post", mock_post):
            provider = GeminiFlashProseProvider(
                transport_mode=TransportMode.API,
                api_key="test-api-key-12345",
                model_name="gemini-3.8-flash",
            )
            output = provider.generate_rewrite(self.request, prompt="Rewrite prompt")

            self.assertEqual(
                output,
                "Gloria the flamingo lamp shuddered as the shelf-like tie-dye hips struck."
            )
            self.assertEqual(len(provider.receipts), 1)
            receipt = provider.receipts[0]
            self.assertEqual(receipt.status, "success")
            self.assertEqual(receipt.transport_mode, TransportMode.API)
            self.assertEqual(receipt.model_name, "gemini-3.8-flash")

    def test_07_api_transport_http_error(self):
        """Simulated HTTP error raises ProviderExecutionError and logs error receipt."""
        mock_post = MagicMock()
        mock_post.return_value.status_code = 429
        mock_post.return_value.text = "RESOURCE_EXHAUSTED: Rate limit exceeded"

        with patch("httpx.post", mock_post):
            provider = GeminiFlashProseProvider(
                transport_mode=TransportMode.API,
                api_key="test-api-key-12345",
            )
            with self.assertRaises(ProviderExecutionError) as ctx:
                provider.generate_rewrite(self.request, prompt="prompt")
            self.assertIn("HTTP 429", str(ctx.exception))

            self.assertEqual(len(provider.receipts), 1)
            self.assertEqual(provider.receipts[0].status, "error")

    def test_08_provider_factory(self):
        """Factory creates correct provider types."""
        mock_p = create_prose_provider("mock")
        self.assertIsInstance(mock_p, MockProseProvider)

        sess_p = create_prose_provider("session", session_handler=lambda p: "ok")
        self.assertIsInstance(sess_p, GeminiFlashProseProvider)
        self.assertEqual(sess_p.transport_mode, TransportMode.SESSION)

        api_p = create_prose_provider("api", api_key="abc")
        self.assertIsInstance(api_p, GeminiFlashProseProvider)
        self.assertEqual(api_p.transport_mode, TransportMode.API)

        with self.assertRaises(ValueError):
            create_prose_provider("invalid_mode")


if __name__ == "__main__":
    unittest.main()
