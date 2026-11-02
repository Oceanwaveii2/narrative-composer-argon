"""
Pydantic schemas for behavioral trait extraction from source media.
Enforces typed extraction of kinematics, idiolect, status moves,
and dialectic rationalization patterns with timestamp provenance.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class BehavioralTrait(BaseModel):
    """
    An abstracted behavioral mechanic (physical blocking, vocal cadence,
    status transaction, or rationalization tactic).
    Carries explicit evidence timestamp boundaries.
    """
    category: str = Field(
        ...,
        description="Category: 'kinematics', 'idiolect', 'status_move', or 'rationalization'",
    )
    trait: str = Field(
        ...,
        description=(
            "Abstracted behavioral rule or physical technique. "
            "Must NOT quote spoken lines or namedrop real-world source shows."
        ),
    )
    evidence_start: float = Field(
        ...,
        description="Start timecode in seconds within source media where this behavior occurs.",
    )
    evidence_end: float = Field(
        ...,
        description="End timecode in seconds within source media where this behavior occurs.",
    )
    example_paraphrase: Optional[str] = Field(
        None,
        description=(
            "Synthetic in-character demonstration of the technique "
            "without quoting the source dialogue."
        ),
    )

    @model_validator(mode="after")
    def validate_timestamps(self) -> "BehavioralTrait":
        if self.evidence_end < self.evidence_start:
            raise ValueError(
                f"evidence_end ({self.evidence_end}) cannot be less than evidence_start ({self.evidence_start})"
            )
        return self


class CharacterObservation(BaseModel):
    """Behavioral extraction for a specific character observed in a scene."""
    character_id: str = Field(
        ...,
        description="Normalized character identifier (e.g. 'hayley', 'christ_kardashia', 'holly')",
    )
    kinematics: List[BehavioralTrait] = Field(
        default_factory=list,
        description="Physical posture, center of gravity, gesture mechanics, displacement.",
    )
    idiolect: List[BehavioralTrait] = Field(
        default_factory=list,
        description="Vocal fry, vowel elongation, pitch shifts, cadence, syntax habits.",
    )
    status_moves: List[BehavioralTrait] = Field(
        default_factory=list,
        description="Dominance displays, unbothered deflections, dismissive praises.",
    )
    rationalization_patterns: List[BehavioralTrait] = Field(
        default_factory=list,
        description="How the character justifies an absurd act using moral/aesthetic framing.",
    )

    def all_traits(self) -> List[BehavioralTrait]:
        """Flattens all traits into a single list."""
        return (
            self.kinematics
            + self.idiolect
            + self.status_moves
            + self.rationalization_patterns
        )


class SceneObservation(BaseModel):
    """Complete behavioral extraction package for a single scene window."""
    scene_id: str = Field(..., description="Scene ID from scenes.json (e.g. 'scene_002')")
    source_id: str = Field(..., description="Source ID (e.g. 'kardashian_inflate', 'hot_scoomp_s18e11')")
    window_start: float = Field(..., description="Scene start timecode in seconds")
    window_end: float = Field(..., description="Scene end timecode in seconds")
    characters: List[CharacterObservation] = Field(
        default_factory=list,
        description="List of characters observed in this scene window.",
    )

    def total_trait_count(self) -> int:
        return sum(len(c.all_traits()) for c in self.characters)
