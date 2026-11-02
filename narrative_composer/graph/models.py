"""
Pydantic v2 data models for the Narrative Node Graph (NNG).
Implements definitions, instances, annotations, violations, and suggestions.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self
from narrative_composer.graph.data_ports import DataPort, named_port

from narrative_composer.graph.ids import (
    is_valid_id,
    parse_id,
    state_id,
    xform_id,
)

SCHEMA_VERSION: int = 1


class CueAlias(BaseModel):
    """Maps a script speaker cue to an implied state."""
    cue: str = Field(..., description="Uppercase speaker cue, e.g. 'STEVE', 'RAINEE-PETER'")
    state: Optional[str] = Field(None, description="State slug this cue implies")
    canons: List[str] = Field(default_factory=list, description="Empty = active in all canons")


class StateDef(BaseModel):
    model_config = {'extra': 'allow'}
    """Definition of a distinct narrative/physical form or condition of an entity."""
    id: str = Field(..., description="Canonical ID: <entity>.state.<slug>")
    slug: str = Field(..., description="Short identifier slug (e.g. 'nerd_20')")
    label: str = Field(..., description="Human-readable state name")
    order: int = Field(default=0, description="Progression sort order")
    status: Literal["active", "deprecated"] = Field(default="active")
    canons: List[str] = Field(default_factory=list, description="Active canons (empty = all)")
    cue_aliases: List[CueAlias] = Field(default_factory=list)
    enter_patterns: List[str] = Field(default_factory=list, description="Regex patterns matched on action text")
    observation_patterns: List[str] = Field(default_factory=list, description="Source markers that propose, but do not approve, a state")
    visual_anchors: List[str] = Field(default_factory=list, description="Key anchor terms expected in prose")
    voice_profile: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    data_port: DataPort = Field(default_factory=DataPort)

    @model_validator(mode="after")
    def validate_state_id(self) -> Self:
        named_port(self.data_port, self.id)
        if self.data_port.mode == 'inherit' and self.data_port.bindings:
            raise ValueError('Select extend, override or replace before binding form-local data')
        if not is_valid_id(self.id):
            raise ValueError(f"State ID {self.id!r} is not a valid canonical ID.")
        parsed = parse_id(self.id)
        if parsed.get("kind") != "state":
            raise ValueError(f"State ID {self.id!r} must have kind 'state', got {parsed.get('kind')!r}")
        if parsed.get("slug") != self.slug:
            raise ValueError(f"State ID slug {parsed.get('slug')!r} must match slug attribute {self.slug!r}")
        return self


class TransformDef(BaseModel):
    model_config = {'extra': 'allow'}
    """Definition of a valid transition edge between two states of an entity."""
    id: str = Field(..., description="Canonical ID: <entity>.xform.<from_slug>__<to_slug>")
    from_state: str = Field(..., description="Full state ID of departure")
    to_state: str = Field(..., description="Full state ID of arrival")
    triggers: List[str] = Field(default_factory=list, description="Causal triggers (e.g. 'pink_cube')")
    reversible: bool = Field(default=False)
    status: Literal["active", "deprecated"] = Field(default="active")
    canons: List[str] = Field(default_factory=list, description="Active canons (empty = all)")
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_transform_id(self) -> Self:
        if not is_valid_id(self.id):
            raise ValueError(f"Transform ID {self.id!r} is not a valid canonical ID.")
        parsed_from = parse_id(self.from_state)
        parsed_to = parse_id(self.to_state)

        if parsed_from.get("kind") != "state" or parsed_to.get("kind") != "state":
            raise ValueError("Transform endpoints must be state IDs.")

        from_entity = parsed_from.get("entity")
        to_entity = parsed_to.get("entity")
        if from_entity != to_entity:
            raise ValueError(f"Cross-entity transformations forbidden: {from_entity} != {to_entity}")

        expected_id = xform_id(from_entity, parsed_from["slug"], parsed_to["slug"])
        if self.id != expected_id:
            raise ValueError(f"Transform ID {self.id!r} does not match expected {expected_id!r}")
        return self


class EntityDef(BaseModel):
    model_config = {'extra': 'allow'}
    """Top-level definition of a single unified character entity holding all its states."""
    schema_version: int = Field(default=SCHEMA_VERSION)
    entity_id: str = Field(..., description="Canonical entity slug (e.g. 'stella', 'rainee')")
    display_name: str
    aliases: List[str] = Field(default_factory=list)
    canons: List[str] = Field(default_factory=list)
    base_state: str = Field(..., description="Slug of default/starting state")
    states: List[StateDef] = Field(default_factory=list)
    transforms: List[TransformDef] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    data_port: DataPort = Field(default_factory=DataPort)

    @model_validator(mode="after")
    def validate_entity(self) -> Self:
        named_port(self.data_port, self.entity_id)
        if not is_valid_id(self.entity_id):
            raise ValueError(f"Entity ID {self.entity_id!r} is not a valid canonical ID.")

        slug_set = set()
        for state in self.states:
            parsed = parse_id(state.id)
            if parsed.get("entity") != self.entity_id:
                raise ValueError(
                    f"State {state.id!r} belongs to entity {parsed.get('entity')!r}, not {self.entity_id!r}"
                )
            if state.slug in slug_set:
                raise ValueError(f'Duplicate state: {state.id}')
            slug_set.add(state.slug)

        for xf in self.transforms:
            parsed = parse_id(xf.id)
            if parsed.get("entity") != self.entity_id:
                raise ValueError(
                    f"Transform {xf.id!r} belongs to entity {parsed.get('entity')!r}, not {self.entity_id!r}"
                )
            state_ids = {state.id for state in self.states}
            if xf.from_state not in state_ids or xf.to_state not in state_ids:
                raise ValueError(f'Missing transform endpoint: {xf.id}')
        if len({xf.id for xf in self.transforms}) != len(self.transforms):
            raise ValueError('Duplicate transform ID')

        if self.states and self.base_state not in slug_set:
            raise ValueError(
                f"Base state {self.base_state!r} not found in states of {self.entity_id}: {slug_set}"
            )
        return self


class Annotation(BaseModel):
    """External semantic context or lore attached to an entity, state, or transform."""
    id: str = Field(..., description="Canonical annotation ID: ann.<target>.<n>")
    target_id: str = Field(..., description="Target node ID")
    source: str = Field(..., description="Origin doc or author (e.g. 'ling_au_recompute')")
    kind: Literal["lore", "visual", "voice", "relationship_hint", "style", "note"]
    text: str
    tags: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0)
    canons: List[str] = Field(default_factory=list)
    status: Literal["active", "deprecated"] = Field(default="active")

    @model_validator(mode="after")
    def validate_annotation_ids(self) -> Self:
        if not is_valid_id(self.id):
            raise ValueError(f"Annotation ID {self.id!r} is not a valid canonical ID.")
        if not is_valid_id(self.target_id):
            raise ValueError(f"Annotation target_id {self.target_id!r} is not a valid canonical ID.")
        return self


class StoryTime(BaseModel):
    """Chronological coordinate in screenplay story time."""
    scene_index: int = Field(..., description="0-indexed scene number")
    line: int = Field(..., description="Screenplay script line number")


class StateInstance(BaseModel):
    """An empirical instantiation of a state in a specific script run."""
    id: str
    entity: str
    state_id: str
    at: StoryTime
    source: Literal["explicit", "inferred_intermediate", "base", "initial", "reviewed"]
    evidence: str = ""


class TransformInstance(BaseModel):
    """An empirical instantiation of a transition in a specific script run."""
    id: str
    entity: str
    xform_id: Optional[str] = Field(None, description="None indicates an illegal/unsupported jump")
    from_state: str
    to_state: str
    at: StoryTime
    source: Literal["explicit", "inferred_intermediate", "unverified_observation"]
    evidence: str = ""


class Violation(BaseModel):
    """A lint or graph consistency violation."""
    rule_id: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    line: Optional[int] = None
    entity: Optional[str] = None
    message: str
    suggestion: str = ""


class Suggestion(BaseModel):
    """Context-specific story/prose enhancement advice."""
    kind: str
    line: Optional[int] = None
    entity: Optional[str] = None
    text: str
    context_node_ids: List[str] = Field(default_factory=list)
