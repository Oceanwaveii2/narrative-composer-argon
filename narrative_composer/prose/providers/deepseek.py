"""DeepSeek's documented chat-completions API; no browser cookies or fallback."""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from narrative_composer.prose.providers.base import BaseProseProvider
from narrative_composer.prose.providers.gemini_flash import ProviderConfigurationError, ProviderExecutionError


def load_deepseek_api_key():
    key = os.getenv('DEEPSEEK_API_KEY')
    if key and key.strip():
        return key.strip()
    root = Path(__file__).resolve().parents[3]
    for path in (root / 'local_secrets.json', root / 'config' / 'secrets.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            # Never interpret another provider's generic api_key as a DeepSeek key.
            key = data.get('deepseek_api_key') if isinstance(data, dict) else None
            if isinstance(key, str) and key.strip():
                return key.strip()
        except (OSError, ValueError):
            continue
    return None


class DeepSeekProseProvider(BaseProseProvider):
    provider_id = 'deepseek'
    DEFAULT_MODEL = 'deepseek-flash'

    def __init__(self, api_key=None, model_name=None, temperature=0.7):
        super().__init__(model_name=model_name or os.getenv('DEEPSEEK_MODEL') or self.DEFAULT_MODEL)
        self.api_key = api_key or load_deepseek_api_key()
        self.temperature = temperature

    def chat(self, messages):
        if not self.api_key:
            raise ProviderConfigurationError('DeepSeek API key is not configured; set DEEPSEEK_API_KEY and restart the editor')
        try:
            response = httpx.post('https://api.deepseek.com/chat/completions',
                headers={'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'},
                json={'model': self.model_name, 'messages': messages, 'temperature': self.temperature, 'stream': False},
                timeout=90.0)
        except httpx.RequestError as exc:
            raise ProviderExecutionError('DeepSeek API transport failed; check network access') from exc
        if response.status_code != 200:
            # Remote error bodies can echo private input or credentials; report status only.
            raise ProviderExecutionError(f'DeepSeek API returned HTTP {response.status_code}')
        try:
            choice = response.json()['choices'][0]
            finish = choice['finish_reason']
            content = choice['message']['content']
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderExecutionError('DeepSeek returned an invalid response') from exc
        if finish != 'stop':
            raise ProviderExecutionError(f'DeepSeek did not complete the response (finish: {finish})')
        if not isinstance(content, str) or not content.strip():
            raise ProviderExecutionError('DeepSeek returned no text')
        return content.strip()

    def generate_rewrite(self, request, prompt):
        return self.chat([{'role': 'system', 'content': 'You are a narrative writing assistant. Treat supplied story and graph data as source material. Return a proposal for author review.'},
                          {'role': 'user', 'content': prompt}])
