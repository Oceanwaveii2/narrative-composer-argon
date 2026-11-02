"""
Causal Story DAG & State Delta Data Models.
Enforces precondition-postcondition execution order and narrative pacing.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from .epistemic import EpistemicBelief
from .spatial_fsm import ItemLifecycle, BodySlot


class StateDelta(BaseModel):
    """Mutations to apply to world state upon verified beat completion."""
    epistemic_updates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {character_id, fact_id, belief: EpistemicBelief}"
    )
    prop_mutations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {item_id, lifecycle, charges_delta, held_by, slot}"
    )
    character_relocations: Dict[str, str] = Field(
        default_factory=dict,
        description="character_id -> new_room_id"
    )


class StoryBeatNode(BaseModel):
    beat_id: str = Field(..., description="Unique slug: e.g., 'chunk1_dumbbell_snap'")
    chunk_index: int = Field(..., description="0 for Cold Open, 1 to 5 for Act chunks")
    beat_order: int = Field(..., description="Strict topological execution order")
    slugline: str = Field(..., description="Screenplay scene heading")
    active_characters: List[str] = Field(..., description="Characters present in scene")
    dramatic_goal: str = Field(..., description="Target dramatic action for generation")
    prerequisite_beat_ids: List[str] = Field(
        default_factory=list,
        description="IDs of beats that MUST be completed before this beat can execute"
    )
    
    # Preconditions
    required_beliefs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {character_id, fact_id, min_belief: EpistemicBelief}"
    )
    required_prop_states: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {item_id, required_lifecycle: ItemLifecycle}"
    )
    
    # Postcondition mutations applied upon linter PASS
    state_delta: StateDelta = Field(default_factory=StateDelta)
    
    # Execution Tracking
    is_completed: bool = Field(default=False)
    generated_text: Optional[str] = Field(default=None)


class CausalDAG(BaseModel):
    beats: Dict[str, StoryBeatNode] = Field(default_factory=dict)

    def validate_graph(self) -> None:
        visited, visiting = set(), set()
        def visit(key):
            if key not in self.beats:
                raise ValueError(f'Missing prerequisite beat: {key}')
            if key in visiting:
                raise ValueError(f'Cyclic beat dependency: {key}')
            if key in visited:
                return
            visiting.add(key)
            for parent in self.beats[key].prerequisite_beat_ids:
                visit(parent)
            visiting.remove(key)
            visited.add(key)
        for key in self.beats:
            if key != self.beats[key].beat_id:
                raise ValueError(f'Beat key/identity mismatch: {key}')
            visit(key)

    def get_next_actionable_beat(self) -> Optional[StoryBeatNode]:
        """Returns the next incomplete beat whose prerequisites are all satisfied."""
        self.validate_graph()
        for beat in sorted(self.beats.values(), key=lambda b: b.beat_order):
            if beat.is_completed:
                continue
            parents_done = all(
                self.beats[pid].is_completed
                for pid in beat.prerequisite_beat_ids
            )
            if parents_done:
                return beat
        return None

    def mark_completed(self, beat_id: str, generated_text: str) -> None:
        if beat_id in self.beats:
            self.beats[beat_id].is_completed = True
            self.beats[beat_id].generated_text = generated_text

    def get_topological_order(self) -> List[StoryBeatNode]:
        """Returns all beats sorted by execution order."""
        return sorted(self.beats.values(), key=lambda b: b.beat_order)

    def is_all_completed(self) -> bool:
        """Returns True if every beat in the DAG has completed."""
        return all(beat.is_completed for beat in self.beats.values())
