"""Explicit request limits; byte limits are not token or dollar estimates."""
from __future__ import annotations

import json

from narrative_composer.prose.providers.gemini_flash import ProviderConfigurationError

DEFAULT_MAX_INPUT_BYTES = 65536
DEFAULT_MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_BYTES = 262144
MAX_OUTPUT_TOKENS = 32768


def positive_limit(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ProviderConfigurationError(f"{name} must be an integer from 1 to {maximum}")
    return value


def check_messages_size(messages, maximum):
    """Reject oversized input before transport; never truncate authored context."""
    size = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > maximum:
        raise ProviderConfigurationError(
            f"Request messages contain {size} UTF-8 bytes; the configured limit is {maximum}. "
            "Select a smaller passage or explicitly configure a larger bounded limit."
        )
    return size


def check_prompt_size(prompt, maximum):
    size = len(prompt.encode("utf-8"))
    if size > maximum:
        raise ProviderConfigurationError(
            f"Request prompt contains {size} UTF-8 bytes; the configured limit is {maximum}. "
            "Select a smaller passage or explicitly configure a larger bounded limit."
        )
    return size
