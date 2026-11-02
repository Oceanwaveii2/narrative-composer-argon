"""
Standalone Export and Import for Narrative Node Graph (NNG).
Enables any state or transformation path to be exported as a minimal seed for side stories.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import copy
import json

from narrative_composer.graph.ids import parse_id
from narrative_composer.graph.models import (
    Annotation,
    EntityDef,
    StateDef,
    TransformDef,
    SCHEMA_VERSION,
)
from narrative_composer.graph.graph import StoryGraph


def export_standalone(
    graph: StoryGraph,
    entity: Union[str, EntityDef],
    from_state_slug: str,
    to_state_slug: Optional[str] = None,
    canon: Optional[str] = None,
    include_annotations: bool = True,
    world: Any = None,
) -> Dict[str, Any]:
    """
    Exports a standalone seed for an entity starting at from_state_slug and
    optionally following the shortest valid path to to_state_slug.
    Preserves canonical IDs without mutation.
    """
    if isinstance(entity, EntityDef):
        entity_id = entity.entity_id
        entity_def = entity
    else:
        entity_id = str(entity)
        entity_def = graph.get_entity(entity_id)

    # Resolve from_slug and from_state_id
    if from_state_slug.startswith(f"{entity_id}.state."):
        from_slug = parse_id(from_state_slug)["slug"]
        from_state_id = from_state_slug
    else:
        from_slug = from_state_slug
        from_state_id = f"{entity_id}.state.{from_slug}"

    start_st = graph.get_state(from_state_id)
    if canon is not None and start_st.canons and canon not in start_st.canons:
        raise ValueError(
            f"State {from_state_id!r} is not valid in canon {canon!r}"
        )

    # Determine states and transforms on path
    if to_state_slug is None:
        selected_states = [copy.deepcopy(start_st)]
        selected_transforms = []
        selected_state_ids = {from_state_id}
        selected_xform_ids = set()
    else:
        if to_state_slug.startswith(f"{entity_id}.state."):
            to_slug = parse_id(to_state_slug)["slug"]
            to_state_id = to_state_slug
        else:
            to_slug = to_state_slug
            to_state_id = f"{entity_id}.state.{to_slug}"

        goal_st = graph.get_state(to_state_id)
        if canon is not None and goal_st.canons and canon not in goal_st.canons:
            raise ValueError(
                f"State {to_state_id!r} is not valid in canon {canon!r}"
            )

        if from_slug == to_slug:
            selected_states = [copy.deepcopy(start_st)]
            selected_transforms = []
            selected_state_ids = {from_state_id}
            selected_xform_ids = set()
        else:
            path = graph.find_path(from_state_id, to_state_id, canon=canon)
            if path is None or len(path) == 0:
                raise ValueError(
                    f"No path found for entity {entity_id!r} from {from_slug!r} to {to_slug!r} in canon {canon!r}"
                )

            selected_xforms = [graph.get_xform(xid) for xid in path]
            selected_xform_ids = set(path)

            needed_state_ids = {from_state_id, to_state_id}
            for xf in selected_xforms:
                needed_state_ids.add(xf.from_state)
                needed_state_ids.add(xf.to_state)

            selected_state_ids = needed_state_ids
            # Keep states sorted by their original order or progression
            all_entity_states = [s for s in entity_def.states if s.id in selected_state_ids]
            selected_states = [copy.deepcopy(s) for s in all_entity_states]
            selected_transforms = [copy.deepcopy(xf) for xf in selected_xforms]

    # Minimal EntityDef
    minimal_entity = EntityDef(
        schema_version=entity_def.schema_version,
        entity_id=entity_def.entity_id,
        display_name=entity_def.display_name,
        aliases=list(entity_def.aliases),
        canons=[canon] if canon else list(entity_def.canons),
        base_state=from_slug,
        states=selected_states,
        transforms=selected_transforms,
        attributes=copy.deepcopy(entity_def.attributes),
    )

    # Active annotations targeting those IDs
    export_annotations: Dict[str, Dict[str, Any]] = {}
    if include_annotations:
        target_ids = {entity_id} | selected_state_ids | selected_xform_ids
        for aid, ann in graph.annotations.items():
            if ann.status != "active":
                continue
            if ann.target_id not in target_ids:
                continue
            if canon is not None and ann.canons and canon not in ann.canons:
                continue
            export_annotations[aid] = ann.model_dump()

    result: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "standalone_seed",
        "entity": minimal_entity.model_dump(),
        "annotations": export_annotations,
    }

    if canon is not None:
        result["canon"] = canon

    # World relationships and facts if provided
    if world is not None:
        result["world"] = {
            "relationships": world.relationships(entity_id, canon=canon),
            "facts": world.facts(entity_id, canon=canon),
        }

    return result


def import_standalone(data: Union[Dict[str, Any], str, Path]) -> StoryGraph:
    """
    Imports a standalone seed dictionary, JSON string, or file path into a StoryGraph.
    """
    if isinstance(data, (str, Path)):
        p = Path(data)
        if p.exists():
            payload = json.loads(p.read_text(encoding="utf-8"))
        else:
            payload = json.loads(str(data))
    else:
        payload = data

    if payload.get("kind") != "standalone_seed":
        raise ValueError(
            f"Expected payload kind 'standalone_seed', got {payload.get('kind')!r}"
        )

    entity_raw = payload.get("entity")
    if not entity_raw:
        raise ValueError("Missing 'entity' definition in standalone seed.")

    if isinstance(entity_raw, dict):
        entity_def = EntityDef.model_validate(entity_raw)
    elif isinstance(entity_raw, EntityDef):
        entity_def = entity_raw
    else:
        raise ValueError(f"Invalid entity format: {type(entity_raw)}")

    entities = {entity_def.entity_id: entity_def}

    annotations: Dict[str, Annotation] = {}
    raw_ann = payload.get("annotations", {})
    if isinstance(raw_ann, dict):
        for aid, adata in raw_ann.items():
            ann = Annotation.model_validate(adata) if isinstance(adata, dict) else adata
            annotations[ann.id] = ann
    elif isinstance(raw_ann, list):
        for adata in raw_ann:
            ann = Annotation.model_validate(adata) if isinstance(adata, dict) else adata
            annotations[ann.id] = ann

    return StoryGraph(entities=entities, annotations=annotations)
