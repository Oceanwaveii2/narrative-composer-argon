"""
Super-JSON Character Node Models (Lightweight Fiction Engine Node).
Encodes dialectic character profiles (Thesis vs Antithesis -> Synthesis),
kinematics, idiolect, status moves, and exact empirical provenance.
"""

import copy
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Ground-truth video and transcript evidence anchoring a behavioral trait."""
    source_id: str = Field(..., description="Source ID (e.g. 'hot_scoomp_s18e11', 'kardashian_inflate')")
    scene_id: str = Field(..., description="Scene ID from scenes.json (e.g. 'scene_002')")
    evidence_start: float = Field(..., description="Start timestamp in seconds")
    evidence_end: float = Field(..., description="End timestamp in seconds")
    frame_ref: Optional[str] = Field(None, description="Optional path to representative keyframe")


class DialecticTrait(BaseModel):
    """
    An abstracted behavioral trait carrying confidence scores and provenance.
    """
    trait_id: str = Field(..., description="Unique slug for the trait")
    category: str = Field(..., description="'kinematics', 'idiolect', 'status_move', or 'rationalization'")
    description: str = Field(..., description="Abstracted technique or behavioral dynamic")
    provenance: List[Provenance] = Field(default_factory=list)
    recurrence_count: Optional[int] = Field(1, description="Number of independent scenes this trait was observed in; null if unknown")
    confidence_score: Optional[float] = Field(1.0, description="Confidence rating between 0.0 and 1.0; null if uncalibrated")
    example_expression: Optional[str] = Field(None, description="In-character expression of the trait")


class DialecticPole(BaseModel):
    """One pole of a character's internal dialectic tension."""
    pole_name: str = Field(..., description="Name of the pole (e.g. 'Thesis: Crunchy Activist')")
    core_drive: str = Field(..., description="Primary subconscious desire or moral posture")
    vocabulary_domain: List[str] = Field(default_factory=list, description="Key lexicon terms associated with this pole")
    traits: List[DialecticTrait] = Field(default_factory=list)


class SynthesisRule(BaseModel):
    """Comedic logic dictating how opposing dialectic poles collide in behavior."""
    rule_id: str
    trigger: str = Field(..., description="Scene situation that triggers this synthesis")
    mechanism: str = Field(..., description="How Thesis and Antithesis fuse to create comedic behavior")
    example_volley: Optional[str] = Field(None, description="Example dialogue/action demonstrating the synthesis, if supplied")


class DialecticCharacterNode(BaseModel):
    """
    Complete Super-JSON Lite Character Node.
    Serves as the behavioral engine driving character generation and linter enforcement.
    """
    character_id: str = Field(..., description="Canonical ID (e.g. 'hayley')")
    display_name: str = Field(..., description="Human-readable name")
    version: str = Field("1.0.0", description="Semantic schema version")
    thesis: DialecticPole
    antithesis: DialecticPole
    synthesis_rules: List[SynthesisRule] = Field(default_factory=list)
    kinematics: List[DialecticTrait] = Field(default_factory=list)
    idiolect: List[DialecticTrait] = Field(default_factory=list)
    status_moves: List[DialecticTrait] = Field(default_factory=list)

    def all_traits(self) -> List[DialecticTrait]:
        """Collects all traits across kinematics, idiolect, status, thesis, and antithesis."""
        return (
            self.kinematics
            + self.idiolect
            + self.status_moves
            + self.thesis.traits
            + self.antithesis.traits
        )

    def to_prompt_directive(self, token_budget: int = 120) -> str:
        """
        Synthesizes a high-density, low-token behavioral directive for the generator prompt.
        Uses only supplied profile data; no universal persona or source-safety guarantee.
        """
        parts = [
            f"[{self.display_name.upper()} BEHAVIORAL ENGINE]",
            f"INTERNAL CONFLICT: {self.thesis.core_drive} vs {self.antithesis.core_drive}.",
            f"THEMATIC DOMAINS: {', '.join(self.thesis.vocabulary_domain[:4])}; {', '.join(self.antithesis.vocabulary_domain[:4])}.",
            "KINEMATICS: " + "; ".join(t.description for t in self.kinematics[:2]),
            "IDIOLECT: " + "; ".join(t.description for t in self.idiolect[:2]),
            "STATUS: " + "; ".join(t.description for t in self.status_moves[:2]),
        ]
        parts.extend(f"COMEDIC SYNTHESIS: when {r.trigger}: {r.mechanism}" for r in self.synthesis_rules)
        # Approximate character budget only; actual provider tokenization differs.
        return "\n".join(parts)[:max(0, token_budget) * 4]

    @classmethod
    def load_from_json(cls, file_path: str) -> "DialecticCharacterNode":
        """Loads a DialecticCharacterNode from a JSON file path."""
        from pathlib import Path
        p = Path(file_path)
        import json
        return parse_compatible_profile(json.loads(p.read_text(encoding="utf-8")))

    @classmethod
    def load_directory(cls, dir_path: str) -> Dict[str, "DialecticCharacterNode"]:
        """Loads all character JSON files from a directory into a dict keyed by lowercase character_id."""
        from pathlib import Path
        p = Path(dir_path)
        nodes: Dict[str, DialecticCharacterNode] = {}
        if p.exists() and p.is_dir():
            for json_file in p.glob("*.json"):
                try:
                    node = cls.load_from_json(str(json_file))
                    nodes[node.character_id.lower()] = node
                except Exception:
                    pass
        return nodes


def parse_compatible_profile(raw: dict) -> DialecticCharacterNode:
    """Adapt legacy string traits in memory without changing their source record.

    Legacy descriptions have no evidence timestamps or measured confidence, so the
    normalized view explicitly leaves those fields unknown rather than inventing them.
    """
    data = copy.deepcopy(raw)
    if not isinstance(data, dict):
        raise ValueError('Profile must be an object')
    for field_name in ('kinematics', 'idiolect', 'status_moves'):
        values = data.get(field_name, [])
        if not isinstance(values, list):
            continue
        normalized = []
        for index, value in enumerate(values):
            if isinstance(value, str):
                code = hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]
                normalized.append({'trait_id': f'legacy_{field_name}_{code}_{index + 1}',
                    'category': field_name, 'description': value, 'provenance': [],
                    'recurrence_count': None, 'confidence_score': None})
            else:
                normalized.append(value)
        data[field_name] = normalized
    return DialecticCharacterNode.model_validate(data)
