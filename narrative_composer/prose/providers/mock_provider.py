"""
Synthetic mock provider for headless, deterministic M1 testing.
Requires no network, API key, browser session, or GPU.
"""

from typing import Optional
from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.providers.base import BaseProseProvider


class MockProseProvider(BaseProseProvider):
    """
    Deterministic synthetic prose generator.
    By default, generates valid prose that preserves all required protected tokens.
    Can be configured to drop tokens to test negative verification gates.
    """

    def __init__(
        self,
        canned_response: Optional[str] = None,
        drop_protected: bool = False,
        model_name: str = "synthetic-mock-v1"
    ):
        super().__init__(model_name=model_name)
        self.canned_response = canned_response
        self.drop_protected = drop_protected
        self.call_count = 0
        self.last_prompt = ""

    def generate_rewrite(self, request: ProseRewriteRequest, prompt: str) -> str:
        self.call_count += 1
        self.last_prompt = prompt

        if self.canned_response is not None:
            return self.canned_response

        if self.drop_protected:
            # Deliberately omit all protected tokens to trigger rejection
            return "A totally generic scene where nothing noteworthy or canonical occurred."

        # Assemble a deterministic synthetic paragraph containing all required tokens and dialogue
        preserved_tokens = []
        for span in request.protected_spans:
            if span.required_tokens:
                preserved_tokens.extend(span.required_tokens)
            elif span.text:
                preserved_tokens.append(span.text)

        tokens_clause = " ".join(dict.fromkeys(preserved_tokens))
        return (
            f"Under the flickering amber fixtures, {tokens_clause} unfolded in sharp, measured cadence. "
            f"The air smelled of ozone and damp plaster as the blocking resolved."
        )
