"""
Gemini 3.8 Flash prose rewrite provider with dual-mode transport:
1. Official Gemini REST API via httpx/requests (using GEMINI_API_KEY)
2. Interactive Gemini Session transport (via injected session handler)
3. Synthetic deterministic mock fallback (for offline CI/CD)

Enforces:
- Explicit pinned model identity ('gemini-3.8-flash')
- Durable attempt receipts with latency and prompt hashes
- Strict error classification (Configuration vs Execution errors)
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.providers.base import BaseProseProvider


class TransportMode(str, Enum):
    MOCK = "mock"
    SESSION = "session"
    API = "api"


class ProviderError(Exception):
    """Base exception for model provider errors."""
    pass


class ProviderConfigurationError(ProviderError):
    """Raised when required credentials or transport handlers are missing."""
    pass


class ProviderExecutionError(ProviderError):
    """Raised when an API call or session transport fails at runtime."""
    pass


class ProviderReceipt(BaseModel):
    """Durable receipt tracking prompt submission, model identity, latency, and raw output."""
    receipt_id: str
    request_id: str
    prompt_hash: str
    model_name: str
    transport_mode: TransportMode
    latency_ms: float
    raw_response_text: str
    status: str = "success"
    error_message: Optional[str] = None
    reasoning_effort: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GeminiFlashProseProvider(BaseProseProvider):
    """
    Model provider adapter for Gemini 3.8 Flash.
    Supports API keys, interactive session bridges, and offline synthetic test fixtures.
    """

    def __init__(
        self,
        transport_mode: TransportMode = TransportMode.MOCK,
        api_key: Optional[str] = None,
        session_handler: Optional[Callable[[str], str]] = None,
        model_name: str = "gemini-3.8-flash",
        temperature: float = 0.6,
        thinking_budget: int = 0,
        api_base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        super().__init__(model_name=model_name)
        self.transport_mode = transport_mode
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.session_handler = session_handler
        self.temperature = temperature
        self.thinking_budget = thinking_budget
        self.api_base_url = api_base_url
        self.receipts: List[ProviderReceipt] = []

    def generate_rewrite(self, request: ProseRewriteRequest, prompt: str) -> str:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        receipt_id = f"rcpt_{hashlib.sha256(f'{request.request_id}:{time.time()}'.encode('utf-8')).hexdigest()[:12]}"
        start_time = time.perf_counter()

        try:
            if self.transport_mode == TransportMode.MOCK:
                output = self._call_mock(request, prompt)
            elif self.transport_mode == TransportMode.SESSION:
                output = self._call_session(prompt)
            elif self.transport_mode == TransportMode.API:
                output = self._call_api(prompt)
            else:
                raise ProviderConfigurationError(f"Unsupported transport mode: {self.transport_mode}")

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            receipt = ProviderReceipt(
                receipt_id=receipt_id,
                request_id=request.request_id,
                prompt_hash=prompt_hash,
                model_name=self.model_name,
                transport_mode=self.transport_mode,
                latency_ms=latency_ms,
                raw_response_text=output,
                status="success",
            )
            self.receipts.append(receipt)
            return output

        except Exception as err:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            receipt = ProviderReceipt(
                receipt_id=receipt_id,
                request_id=request.request_id,
                prompt_hash=prompt_hash,
                model_name=self.model_name,
                transport_mode=self.transport_mode,
                latency_ms=latency_ms,
                raw_response_text="",
                status="error",
                error_message=str(err),
            )
            self.receipts.append(receipt)
            if isinstance(err, ProviderError):
                raise
            raise ProviderExecutionError(f"Provider transport failure: {err}") from err

    # ========================================================================
    # Transport Implementations
    # ========================================================================

    def _call_mock(self, request: ProseRewriteRequest, prompt: str) -> str:
        """Deterministic synthetic generation preserving required tokens."""
        preserved = []
        for span in request.protected_spans:
            if span.required_tokens:
                preserved.extend(span.required_tokens)
            elif span.text:
                preserved.append(span.text)

        tokens_clause = " ".join(dict.fromkeys(preserved))
        return (
            f"White sparks snapped across the carpet. {tokens_clause} "
            f"The living room smelled of ozone and lavender as the physical blocking held firm."
        )

    def _call_session(self, prompt: str) -> str:
        """Executes rewrite via injected interactive session handler."""
        if not self.session_handler:
            raise ProviderConfigurationError(
                "TransportMode is SESSION, but no session_handler callable was provided."
            )
        try:
            return self.session_handler(prompt)
        except Exception as err:
            raise ProviderExecutionError(f"Session transport error: {err}") from err

    def _call_api(self, prompt: str) -> str:
        """Executes rewrite via Google Gemini REST API using httpx."""
        if not self.api_key:
            raise ProviderConfigurationError(
                "TransportMode is API, but no API key was provided or found in GEMINI_API_KEY environment variable."
            )

        import httpx

        url = f"{self.api_base_url}/models/{self.model_name}:generateContent?key={self.api_key}"
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": 2048,
            },
        }

        try:
            response = httpx.post(url, json=payload, timeout=30.0)
            if response.status_code != 200:
                raise ProviderExecutionError(
                    f"Gemini API returned HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ProviderExecutionError("Gemini API returned no candidates in response.")
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise ProviderExecutionError("Gemini API candidate contained no parts.")
            return parts[0].get("text", "").strip()

        except httpx.RequestError as req_err:
            raise ProviderExecutionError(f"HTTP request to Gemini API failed: {req_err}") from req_err
