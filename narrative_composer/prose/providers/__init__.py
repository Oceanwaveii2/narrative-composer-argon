"""
Prose providers module.
"""

import os
from typing import Any, Optional
from narrative_composer.prose.providers.base import BaseProseProvider
from narrative_composer.prose.providers.mock_provider import MockProseProvider
from narrative_composer.prose.providers.gemini_flash import (
    GeminiFlashProseProvider,
    TransportMode,
    ProviderReceipt,
    ProviderError,
    ProviderConfigurationError,
    ProviderExecutionError,
)
from narrative_composer.prose.providers.venice import VeniceProseProvider
from narrative_composer.prose.providers.codex_session import CodexSessionProseProvider
from narrative_composer.prose.providers.deepseek import DeepSeekProseProvider


def create_prose_provider(
    mode: str = "mock",
    api_key: Optional[str] = None,
    session_handler: Optional[Any] = None,
    model_name: Optional[str] = None,
    **kwargs: Any,
) -> BaseProseProvider:
    """Factory helper to instantiate a configured model provider."""
    normalized_mode = mode.lower().strip()
    if normalized_mode == "mock":
        return MockProseProvider(model_name=model_name or "synthetic-mock-v1", **kwargs)
    elif normalized_mode in ("session", "api", "gemini"):
        transport = TransportMode.SESSION if normalized_mode == "session" else TransportMode.API
        return GeminiFlashProseProvider(
            transport_mode=transport,
            api_key=api_key,
            session_handler=session_handler,
            model_name=model_name or "gemini-3.8-flash",
            **kwargs,
        )
    elif normalized_mode == "venice":
        return VeniceProseProvider(
            api_key=api_key or os.getenv("VENICE_API_KEY"),
            model_name=model_name or "venice-uncensored",
            **kwargs,
        )
    elif normalized_mode == 'deepseek':
        return DeepSeekProseProvider(api_key=api_key, model_name=model_name, **kwargs)
    elif normalized_mode in ('codex', 'terra'):
        return CodexSessionProseProvider(model_name=model_name or 'gpt-6.1-terra', **kwargs)
    else:
        raise ValueError(f"Unknown provider mode: '{mode}'. Choose 'mock', 'codex', 'session', 'api', 'deepseek', or 'venice'.")


__all__ = [
    "BaseProseProvider",
    "MockProseProvider",
    "GeminiFlashProseProvider",
    "VeniceProseProvider",
    "DeepSeekProseProvider",
    "CodexSessionProseProvider",
    "TransportMode",
    "ProviderReceipt",
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderExecutionError",
    "create_prose_provider",
]
