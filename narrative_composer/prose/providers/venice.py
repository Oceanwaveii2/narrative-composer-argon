"""
Venice AI model provider adapter.
Provides OpenAI-compatible inference via Venice AI (https://api.venice.ai/api/v1)
with unrestricted / uncensored creative prose models (e.g. 'venice-uncensored').
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.providers.base import BaseProseProvider
from narrative_composer.prose.providers.request_limits import (
    DEFAULT_MAX_INPUT_BYTES, DEFAULT_MAX_OUTPUT_TOKENS, MAX_INPUT_BYTES,
    MAX_OUTPUT_TOKENS, check_messages_size, positive_limit,
)
from narrative_composer.prose.providers.gemini_flash import (
    ProviderConfigurationError,
    ProviderExecutionError,
    ProviderReceipt,
    TransportMode,
)


DEFAULT_SECRETS_FILENAME = "local_secrets.json"


def _repo_root() -> Path:
    """Locates the project root from this file (narrative_composer/prose/providers/venice.py)."""
    return Path(__file__).resolve().parents[3]


def load_venice_api_key() -> Optional[str]:
    """
    Resolves the Venice API key from, in order:
      1. VENICE_SECRETS_PATH (explicit file override, mainly for tests)
      2. local_secrets.json at the project root (git-ignored)
      3. config/secrets.json at the project root

    The key is never stored in source code.
    """
    candidates: List[Path] = []
    override = os.getenv("VENICE_SECRETS_PATH")
    if override:
        candidates.append(Path(override))
    root = _repo_root()
    candidates.append(root / DEFAULT_SECRETS_FILENAME)
    candidates.append(root / "config" / "secrets.json")

    for path in candidates:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = data.get("venice_api_key") or data.get("api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


class VeniceProseProvider(BaseProseProvider):
    """
    Model provider adapter for Venice AI inference API.
    Compatible with OpenAI-style /chat/completions endpoint.
    """

    DEFAULT_API_URL = "https://api.venice.ai/api/v1"
    DEFAULT_MODEL = "venice-uncensored"

    @staticmethod
    def _response_text(data):
        try:
            choice = data['choices'][0]
            finish = choice.get('finish_reason')
            output = choice['message']['content']
        except (TypeError, IndexError, KeyError, AttributeError) as exc:
            raise ProviderExecutionError('Venice API returned an invalid response') from exc
        if finish is not None and finish != 'stop':
            raise ProviderExecutionError(f'Venice API did not complete the response (finish: {finish})')
        if not isinstance(output, str) or not output.strip():
            raise ProviderExecutionError('Venice API returned no text')
        return output.strip()

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        api_base_url: str = DEFAULT_API_URL,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    ):
        super().__init__(model_name=model_name)
        # Explicit argument > environment variable > local secrets file. Never hardcoded.
        self.api_key = api_key or os.getenv("VENICE_API_KEY") or load_venice_api_key()
        self.temperature = temperature
        self.max_output_tokens = positive_limit(max_output_tokens, 'max_output_tokens', MAX_OUTPUT_TOKENS)
        self.max_input_bytes = positive_limit(max_input_bytes, 'max_input_bytes', MAX_INPUT_BYTES)
        self.api_base_url = api_base_url.rstrip("/")
        self.receipts: List[ProviderReceipt] = []

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Direct text generation via Venice AI."""
        if not self.api_key:
            raise ProviderConfigurationError(
                "VeniceProseProvider requires an API key. Pass api_key or set VENICE_API_KEY environment variable."
            )

        url = f"{self.api_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        sys_content = (
            system_prompt
            or "You are an expert comedic dramatist, kinematic movement analyst, and narrative engine assistant."
        )
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_completion_tokens": self.max_output_tokens,
        }

        check_messages_size(payload['messages'], self.max_input_bytes)
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        if response.status_code != 200:
            raise ProviderExecutionError(f"Venice API returned HTTP {response.status_code}")

        return self._response_text(response.json())

    def generate_rewrite(self, request: ProseRewriteRequest, prompt: str) -> str:
        if not self.api_key:
            raise ProviderConfigurationError(
                "VeniceProseProvider requires an API key. Pass api_key or set VENICE_API_KEY environment variable."
            )

        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        receipt_id = f"rcpt_venice_{hashlib.sha256(f'{request.request_id}:{time.time()}'.encode('utf-8')).hexdigest()[:12]}"
        start_time = time.perf_counter()

        url = f"{self.api_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional narrative prose stylist and script novelizer. Follow all voice guidelines and protected words strictly.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_completion_tokens": self.max_output_tokens,
        }

        try:
            check_messages_size(payload['messages'], self.max_input_bytes)
            response = httpx.post(url, headers=headers, json=payload, timeout=45.0)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if response.status_code != 200:
                raise ProviderExecutionError(f"Venice API returned HTTP {response.status_code}")

            output_text = self._response_text(response.json())

            receipt = ProviderReceipt(
                receipt_id=receipt_id,
                request_id=request.request_id,
                prompt_hash=prompt_hash,
                model_name=self.model_name,
                transport_mode=TransportMode.API,
                latency_ms=latency_ms,
                raw_response_text=output_text,
                status="success",
            )
            self.receipts.append(receipt)
            return output_text

        except Exception as err:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            receipt = ProviderReceipt(
                receipt_id=receipt_id,
                request_id=request.request_id,
                prompt_hash=prompt_hash,
                model_name=self.model_name,
                transport_mode=TransportMode.API,
                latency_ms=latency_ms,
                raw_response_text="",
                status="error",
                error_message=str(err),
            )
            self.receipts.append(receipt)
            if isinstance(err, (ProviderConfigurationError, ProviderExecutionError)):
                raise
            raise ProviderExecutionError(f"Venice API transport failure: {err}") from err
