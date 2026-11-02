"""
Semantic Drive: passage retrieval and reference indexing.
Provides contextually relevant gold-standard passages from the show corpus
to guide the model's tone, pacing, and comedic timing.
"""

import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class ReferencePassage(BaseModel):
    """A gold-standard passage from the show demonstrating proper voice and blocking."""
    passage_id: str
    profile_id: str
    text: str
    scene_type: str = "general"  # e.g. 'dialogue_sparring', 'prop_comedy', 'physical_escalation'
    tags: List[str] = Field(default_factory=list)


class SemanticDrive:
    """Indexes and retrieves reference passages scoped by show profile."""

    def __init__(self):
        # profile_id -> {passage_id: ReferencePassage}
        self._passages_by_profile: Dict[str, Dict[str, ReferencePassage]] = {}

    def add_passage(self, passage: ReferencePassage) -> None:
        """Indexes a reference passage under its profile_id."""
        if passage.profile_id not in self._passages_by_profile:
            self._passages_by_profile[passage.profile_id] = {}
        self._passages_by_profile[passage.profile_id][passage.passage_id] = passage

    def retrieve_passages(
        self,
        profile_id: str,
        query_text: str,
        scene_type: Optional[str] = None,
        max_results: int = 2,
    ) -> List[ReferencePassage]:
        """
        Retrieves top reference passages matching the query context.
        Strictly isolated to profile_id.
        """
        pool = self._passages_by_profile.get(profile_id, {})
        if not pool:
            return []

        query_tokens: Set[str] = set(re.findall(r"\b[a-zA-Z]{4,}\b", query_text.lower()))
        scored: List[tuple[float, ReferencePassage]] = []

        for p in pool.values():
            score = 0.0
            if scene_type and p.scene_type == scene_type:
                score += 3.0

            p_tokens = set(re.findall(r"\b[a-zA-Z]{4,}\b", p.text.lower()))
            overlap = query_tokens.intersection(p_tokens)
            score += float(len(overlap))
            score += 0.5  # Baseline

            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_results]]
