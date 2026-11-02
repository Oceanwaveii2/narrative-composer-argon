"""
Base abstract class for prose model providers.
"""

from abc import ABC, abstractmethod
from narrative_composer.prose.models import ProseRewriteRequest
from narrative_composer.prose.ports import ModelProviderPort


class BaseProseProvider(ModelProviderPort, ABC):
    """Abstract base class ensuring provider consistency."""

    def __init__(self, model_name: str = "base-provider"):
        self.model_name = model_name

    @abstractmethod
    def generate_rewrite(self, request: ProseRewriteRequest, prompt: str) -> str:
        """Subclasses implement specific transport (Gemini session, Gemini API, or mock)."""
        pass
