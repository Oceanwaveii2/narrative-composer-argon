"""
StoryGraph: Central Definition Graph for Narrative Node Graph (NNG).
Holds entities, states, transforms, annotations, and changelog with pathfinding.
"""

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import copy
import json

from narrative_composer.graph.ids import parse_id
from narrative_composer.graph.migrations import migrate
from narrative_composer.graph.models import (
    Annotation,
    EntityDef,
    StateDef,
    TransformDef,
    SCHEMA_VERSION,
)


class StoryGraph:
    """
    Central definition graph tracking character entities, states, transformations,
    semantic annotations, and patch changelogs.
    """

    def __init__(
        self,
        entities: Optional[Dict[str, EntityDef]] = None,
        annotations: Optional[Dict[str, Annotation]] = None,
        changelog: Optional[List[Dict[str, Any]]] = None,
    ):
        self.entities: Dict[str, EntityDef] = entities or {}
        self.annotations: Dict[str, Annotation] = annotations or {}
        self.changelog: List[Dict[str, Any]] = changelog or []

    @classmethod
    def from_registry(cls, registry: Dict[str, EntityDef]) -> "StoryGraph":
        """Constructs a StoryGraph from a loaded entity registry dict."""
        return cls(entities=copy.deepcopy(registry), annotations={}, changelog=[])

    def get_entity(self, entity_id: str) -> EntityDef:
        """Retrieves an entity by entity_id or raises KeyError."""
        if entity_id not in self.entities:
            raise KeyError(f"Entity not found: {entity_id!r}")
        return self.entities[entity_id]

    def get_state(self, state_id: str) -> StateDef:
        """Retrieves a state by canonical state_id or raises KeyError."""
        parsed = parse_id(state_id)
        entity_id = parsed.get("entity")
        if entity_id and entity_id in self.entities:
            for s in self.entities[entity_id].states:
                if s.id == state_id:
                    return s
        raise KeyError(f"State not found: {state_id!r}")

    def get_xform(self, xform_id: str) -> TransformDef:
        """Retrieves a transform by canonical xform_id or raises KeyError."""
        parsed = parse_id(xform_id)
        entity_id = parsed.get("entity")
        if entity_id and entity_id in self.entities:
            for xf in self.entities[entity_id].transforms:
                if xf.id == xform_id:
                    return xf
        raise KeyError(f"Transform not found: {xform_id!r}")

    def states_of(
        self, entity_id: str, canon: Optional[str] = None
    ) -> List[StateDef]:
        """
        Returns active states of an entity, sorted by order, filtered by canon.
        States with empty canons are available in all canons.
        """
        if entity_id not in self.entities:
            return []
        entity = self.entities[entity_id]
        res = []
        for s in entity.states:
            if s.status != "active":
                continue
            if canon is not None and s.canons and canon not in s.canons:
                continue
            res.append(s)
        return sorted(res, key=lambda st: st.order)

    def next_states(
        self, state_id: str, canon: Optional[str] = None
    ) -> List[str]:
        """Returns target state IDs directly reachable from state_id via active transforms."""
        parsed = parse_id(state_id)
        entity_id = parsed.get("entity")
        if not entity_id or entity_id not in self.entities:
            return []

        targets: List[str] = []
        for xf in self.entities[entity_id].transforms:
            if xf.status != "active":
                continue
            if canon is not None and xf.canons and canon not in xf.canons:
                continue
            if xf.from_state == state_id:
                try:
                    to_state = self.get_state(xf.to_state)
                    if to_state.status == "active":
                        if canon is None or not to_state.canons or canon in to_state.canons:
                            targets.append(xf.to_state)
                except KeyError:
                    pass
        return targets

    def find_path(
        self, from_state_id: str, to_state_id: str, canon: Optional[str] = None
    ) -> Optional[List[str]]:
        """
        BFS pathfinding over active transformations.
        Returns ordered list of transform IDs from departure to destination.
        Returns [] if from_state_id == to_state_id.
        Returns None if no legal path exists under the given canon constraint.
        """
        if from_state_id == to_state_id:
            return []

        try:
            start_st = self.get_state(from_state_id)
            goal_st = self.get_state(to_state_id)
        except KeyError:
            return None

        # Verify start and goal states are active and allowed in canon
        if start_st.status != "active" or goal_st.status != "active":
            return None
        if canon is not None:
            if start_st.canons and canon not in start_st.canons:
                return None
            if goal_st.canons and canon not in goal_st.canons:
                return None

        # Extract entity
        from_entity = parse_id(from_state_id).get("entity")
        to_entity = parse_id(to_state_id).get("entity")
        if from_entity != to_entity or not from_entity or from_entity not in self.entities:
            return None

        entity = self.entities[from_entity]
        transforms = [
            xf for xf in entity.transforms
            if xf.status == "active" and (canon is None or not xf.canons or canon in xf.canons)
        ]

        # BFS queue: (current_state_id, [xform_ids_so_far])
        queue: deque[tuple[str, List[str]]] = deque([(from_state_id, [])])
        visited: Set[str] = {from_state_id}

        while queue:
            curr_state, path = queue.popleft()

            if curr_state == to_state_id:
                return path

            for xf in transforms:
                # Forward traversal
                if xf.from_state == curr_state and xf.to_state not in visited:
                    try:
                        nxt_st = self.get_state(xf.to_state)
                        if nxt_st.status == "active" and (canon is None or not nxt_st.canons or canon in nxt_st.canons):
                            visited.add(xf.to_state)
                            queue.append((xf.to_state, path + [xf.id]))
                    except KeyError:
                        pass
                # Reversible backward traversal
                elif xf.reversible and xf.to_state == curr_state and xf.from_state not in visited:
                    try:
                        nxt_st = self.get_state(xf.from_state)
                        if nxt_st.status == "active" and (canon is None or not nxt_st.canons or canon in nxt_st.canons):
                            visited.add(xf.from_state)
                            queue.append((xf.from_state, path + [xf.id]))
                    except KeyError:
                        pass

        return None

    def validate(self) -> List[str]:
        """Validates internal referential integrity across all entities, states, and transforms."""
        errors: List[str] = []
        for eid, entity in self.entities.items():
            state_ids = {s.id for s in entity.states}
            slugs = {s.slug for s in entity.states}

            if entity.base_state not in slugs:
                errors.append(
                    f"Entity {eid!r} base_state {entity.base_state!r} not in states: {slugs}"
                )

            for xf in entity.transforms:
                if xf.from_state not in state_ids:
                    errors.append(
                        f"Transform {xf.id!r} has invalid from_state {xf.from_state!r}"
                    )
                if xf.to_state not in state_ids:
                    errors.append(
                        f"Transform {xf.id!r} has invalid to_state {xf.to_state!r}"
                    )

        for ann_id, ann in self.annotations.items():
            target_id = ann.target_id
            try:
                # Target can be entity, state, or transform
                if target_id in self.entities:
                    continue
                parsed = parse_id(target_id)
                kind = parsed.get("kind")
                if kind == "state":
                    self.get_state(target_id)
                elif kind == "xform":
                    self.get_xform(target_id)
                else:
                    raise ValueError('Annotation target is not an existing entity, state, or transform')
            except Exception:
                errors.append(f"Annotation {ann_id!r} targets nonexistent ID {target_id!r}")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Serializes StoryGraph to a plain JSON-serializable dictionary."""
        return {
            "schema_version": SCHEMA_VERSION,
            "entities": {eid: e.model_dump() for eid, e in self.entities.items()},
            "annotations": {aid: a.model_dump() for aid, a in self.annotations.items()},
            "changelog": self.changelog,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes StoryGraph to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Saves StoryGraph to a JSON file."""
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "StoryGraph":
        """Loads StoryGraph from JSON, automatically applying schema migrations if needed."""
        raw_text = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw_text)
        migrated = migrate(data)

        entities = {
            eid: EntityDef.model_validate(edata)
            for eid, edata in migrated.get("entities", {}).items()
        }
        annotations = {
            aid: Annotation.model_validate(adata)
            for aid, adata in migrated.get("annotations", {}).items()
        }
        changelog = migrated.get("changelog", [])

        return cls(entities=entities, annotations=annotations, changelog=changelog)
