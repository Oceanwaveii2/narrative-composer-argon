"""
Epistemic State & Theory of Mind (ToM) Data Models.
Tracks character knowledge, false beliefs, and token embargoes to prevent information leaks.
"""

from __future__ import annotations
from enum import IntEnum, Enum
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class EpistemicBelief(IntEnum):
    KNOWN_FALSE = -1           # Agent has proved/believes fact is untrue
    UNKNOWN = 0                # Agent has zero awareness of the fact
    KNOWN_TRUE = 1             # Agent knows fact is true (Ground Truth)
    FALSE_BELIEF = 2           # Agent falsely believes fact is true (Deceived/Misled)
    COGNITIVE_SUPPRESSION = 3  # Fact is suppressed by physical transformation or sensory/romantic overload
    AMNESIA_BLANK = 4          # Character has complete blank recall even when directly prompted ("What's a Jeff?")


class FactCategory(str, Enum):
    IDENTITY = "identity"             # e.g., Secret names, alter-egos ("Steve")
    CRIME_EVENT = "crime_event"       # e.g., Who broke Gloria the Flamingo
    BACKSTORY = "backstory"           # e.g., Front-desk zap at HG studio at 2 PM
    COMMERCIAL = "commercial"         # e.g., $500 class price, Lindsay at front desk
    TRANSFORMATION = "transformation" # e.g., Power battery drained into cube
    DOMESTIC_RELATION = "domestic"    # e.g., Marriage to Jeff, domestic responsibilities


class NarrativeFact(BaseModel):
    fact_id: str = Field(..., description="Unique slug: e.g., 'fact_steve_identity'")
    category: FactCategory = Field(default=FactCategory.BACKSTORY)
    ground_truth: bool = Field(default=True, description="Objective truth value in story universe")
    canonical_text: str = Field(..., description="Authoritative summary of the fact")
    embargo_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens strictly forbidden in dialogue/action if fact is UNKNOWN to speaker"
    )


class EpistemicMatrix(BaseModel):
    timestamp: int = Field(default=0, description="Chronological beat index")
    facts: Dict[str, NarrativeFact] = Field(default_factory=dict)
    # beliefs[character_id][fact_id] -> EpistemicBelief
    beliefs: Dict[str, Dict[str, EpistemicBelief]] = Field(default_factory=dict)

    @staticmethod
    def normalize_character_id(character_id: str) -> str:
        """Resolves character aliases to their canonical base character ID."""
        clean = character_id.upper().strip()
        # Clean (CONT'D), (O.S.), (V.O.)
        for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
            clean = clean.replace(suffix, "").strip()

        if "STELLA" in clean or "STEVE" in clean:
            return "STELLA"
        if "HAYLEY" in clean:
            return "HAYLEY"
        if "HOLLY" in clean:
            return "HOLLY"
        if "FRANCINE" in clean:
            return "FRANCINE"
        if "ROGER" in clean:
            return "ROGER"
        if "RAINEE" in clean:
            return "RAINEE"
        if "RECEPTIONIST" in clean:
            return "RECEPTIONIST"
        if "JEFF" in clean:
            return "JEFF"
        return clean

    def get_belief(self, character_id: str, fact_id: str) -> EpistemicBelief:
        char_upper = self.normalize_character_id(character_id)
        return self.beliefs.get(char_upper, {}).get(fact_id, EpistemicBelief.UNKNOWN)

    def set_belief(self, character_id: str, fact_id: str, belief: EpistemicBelief) -> None:
        char_upper = self.normalize_character_id(character_id)
        if char_upper not in self.beliefs:
            self.beliefs[char_upper] = {}
        self.beliefs[char_upper][fact_id] = belief

    def suppress_facts_for_character(
        self,
        character_id: str,
        fact_ids: Optional[List[str]] = None,
        category: Optional[FactCategory] = None
    ) -> List[str]:
        """Transitions facts into COGNITIVE_SUPPRESSION due to sensory/physical overload."""
        char_upper = self.normalize_character_id(character_id)
        suppressed = []
        for fid, fact in self.facts.items():
            if fact_ids and fid in fact_ids:
                self.set_belief(char_upper, fid, EpistemicBelief.COGNITIVE_SUPPRESSION)
                suppressed.append(fid)
            elif category and fact.category == category:
                self.set_belief(char_upper, fid, EpistemicBelief.COGNITIVE_SUPPRESSION)
                suppressed.append(fid)
        return suppressed

    def trigger_amnesic_blank(self, character_id: str, fact_id: str) -> None:
        """Transitions a fact into complete blank amnesia (e.g. 'What is a Jeff?!')."""
        self.set_belief(character_id, fact_id, EpistemicBelief.AMNESIA_BLANK)

    def is_fact_suppressed(self, character_id: str, fact_id: str) -> bool:
        """Returns True if a character has suppressed or amnesic memory of a fact."""
        belief = self.get_belief(character_id, fact_id)
        return belief in (EpistemicBelief.COGNITIVE_SUPPRESSION, EpistemicBelief.AMNESIA_BLANK)

    def get_embargoed_tokens_for_character(self, character_id: str) -> Set[str]:
        """Returns all forbidden tokens for this character based on UNKNOWN, SUPPRESSED, or AMNESIC facts."""
        char_upper = self.normalize_character_id(character_id)
        embargoed: Set[str] = set()
        for fact_id, fact in self.facts.items():
            belief = self.get_belief(char_upper, fact_id)
            if belief in (EpistemicBelief.UNKNOWN, EpistemicBelief.COGNITIVE_SUPPRESSION, EpistemicBelief.AMNESIA_BLANK):
                for token in fact.embargo_tokens:
                    embargoed.add(token.lower())
        return embargoed

    def get_known_facts(self, character_id: str) -> List[NarrativeFact]:
        """Returns all facts verified as KNOWN_TRUE by this character."""
        char_upper = character_id.upper()
        known = []
        for fact_id, fact in self.facts.items():
            if self.get_belief(char_upper, fact_id) == EpistemicBelief.KNOWN_TRUE:
                known.append(fact)
        return known

    def get_false_beliefs(self, character_id: str) -> List[NarrativeFact]:
        """Returns all facts this character holds a FALSE_BELIEF about."""
        char_upper = character_id.upper()
        misconceptions = []
        for fact_id, fact in self.facts.items():
            if self.get_belief(char_upper, fact_id) == EpistemicBelief.FALSE_BELIEF:
                misconceptions.append(fact)
        return misconceptions
