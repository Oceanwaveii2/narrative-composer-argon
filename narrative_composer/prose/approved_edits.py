"""
Author-approved edits ledger and scoped few-shot retrieval.
Provides:
- Storage for human-verified before/after prose improvements
- Strict profile-based isolation (edits from Profile A never leak to Profile B)
- Defect-type and context-sensitive retrieval for few-shot prompt injection
- Optional JSON persistence
"""

import json
import os
import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field
from narrative_composer.prose.ports import ApprovedEditsStorePort


class ApprovedEditPair(BaseModel):
    """An author-approved before-and-after correction used for few-shot guidance."""
    edit_id: str
    profile_id: str  # Must match target show voice profile
    original_text: str
    approved_text: str
    defect_type: str = "general"  # e.g. 'filter_words', 'label_syntax', 'monotonous_cadence', 'sensory_deficit'
    notes: str = ""
    keywords: List[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if not self.keywords and self.original_text:
            # Auto-extract unique lowercase words (>3 chars) as keywords
            words = re.findall(r"\b[a-zA-Z]{4,}\b", self.original_text.lower())
            self.keywords = sorted(set(words))


class ApprovedEditsStore(ApprovedEditsStorePort):
    """
    Profile-isolated storage and retrieval for author-approved edits.
    Guarantees that edits from one profile cannot be retrieved by another.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        # Indexed by profile_id -> {edit_id: ApprovedEditPair}
        self._edits_by_profile: Dict[str, Dict[str, ApprovedEditPair]] = {}

        if self.storage_path and os.path.exists(self.storage_path):
            self._load_from_disk()

    def add_edit(self, edit: ApprovedEditPair) -> None:
        """Stores an approved edit scoped strictly to its profile_id."""
        if edit.profile_id not in self._edits_by_profile:
            self._edits_by_profile[edit.profile_id] = {}
        self._edits_by_profile[edit.profile_id][edit.edit_id] = edit
        self._persist_if_configured()

    def retrieve_relevant_edits(
        self,
        profile_id: str,
        context_text: str,
        defect_types: Optional[List[str]] = None,
        max_results: int = 3,
    ) -> List[ApprovedEditPair]:
        """
        Retrieves top relevant edits for the given context and defect types.
        Strict isolation: Only searches within self._edits_by_profile[profile_id].
        """
        # Profile Isolation Boundary: if profile_id has no edits, returns empty list immediately
        profile_pool = self._edits_by_profile.get(profile_id, {})
        if not profile_pool:
            return []

        context_words: Set[str] = set(re.findall(r"\b[a-zA-Z]{4,}\b", context_text.lower()))
        defect_set: Set[str] = set(defect_types) if defect_types else set()

        scored_edits: List[tuple[float, ApprovedEditPair]] = []

        for edit in profile_pool.values():
            score = 0.0

            # 1. Defect type match (+3.0 points)
            if edit.defect_type in defect_set:
                score += 3.0

            # 2. Keyword overlap with context (+1.0 point per matching keyword)
            overlap = context_words.intersection(edit.keywords)
            score += float(len(overlap))

            # 3. Base score for having an approved example
            score += 0.5

            scored_edits.append((score, edit))

        # Sort by score descending
        scored_edits.sort(key=lambda x: x[0], reverse=True)
        return [pair[1] for pair in scored_edits[:max_results]]

    def count_edits(self, profile_id: Optional[str] = None) -> int:
        """Returns total edit count, optionally filtered by profile."""
        if profile_id:
            return len(self._edits_by_profile.get(profile_id, {}))
        return sum(len(pool) for pool in self._edits_by_profile.values())

    # ========================================================================
    # Persistence Helpers
    # ========================================================================

    def _persist_if_configured(self) -> None:
        if not self.storage_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
        data = {
            prof: {eid: edit.model_dump() for eid, edit in pool.items()}
            for prof, pool in self._edits_by_profile.items()
        }
        temp_path = f"{self.storage_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)
        os.rename(temp_path, self.storage_path)

    def _load_from_disk(self) -> None:
        if not self.storage_path or not os.path.exists(self.storage_path):
            return
        with open(self.storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._edits_by_profile = {
            prof: {eid: ApprovedEditPair.model_validate(raw) for eid, raw in pool.items()}
            for prof, pool in data.items()
        }
