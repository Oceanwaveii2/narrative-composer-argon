"""
Patch Engine for Narrative Node Graph (NNG).
Applies atomic transactional patch operations to the definition graph.
"""

from typing import Any, Dict, List
import copy

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.ids import parse_id
from narrative_composer.graph.models import (
    Annotation,
    CueAlias,
    EntityDef,
    StateDef,
    TransformDef,
)


class PatchError(Exception):
    """Raised when a graph patch operation fails validation."""
    pass


def apply_patch(
    graph: StoryGraph, ops: List[Dict[str, Any]], author: str = "ai"
) -> StoryGraph:
    """
    Applies a list of patch operations atomically to a copy of StoryGraph.
    If any operation fails, raises PatchError and leaves the original graph untouched.
    On success, appends changelog entries and returns the new StoryGraph.
    """
    new_graph = copy.deepcopy(graph)
    log_entries: List[Dict[str, Any]] = []

    for idx, op in enumerate(ops):
        op_name = op.get("op")
        if not op_name:
            raise PatchError(f"Operation #{idx} is missing required 'op' field.")

        if op_name == "add_entity":
            entity_data = op.get("entity")
            if not entity_data:
                raise PatchError("Op add_entity requires 'entity' dict.")
            try:
                entity_def = EntityDef.model_validate(entity_data)
            except Exception as e:
                raise PatchError(f"Invalid entity definition for add_entity: {e}")

            if entity_def.entity_id in new_graph.entities:
                raise PatchError(f"Entity ID {entity_def.entity_id!r} already exists.")

            new_graph.entities[entity_def.entity_id] = entity_def
            log_entries.append({
                "op": "add_entity",
                "target": entity_def.entity_id,
                "author": author,
            })

        elif op_name == "add_state":
            entity_id = op.get("entity")
            state_data = op.get("state")
            if not entity_id or not state_data:
                raise PatchError(f"Op add_state requires 'entity' and 'state' dict.")
            if entity_id not in new_graph.entities:
                raise PatchError(f"Entity {entity_id!r} not found for add_state.")

            try:
                state_def = StateDef.model_validate(state_data)
            except Exception as e:
                raise PatchError(f"Invalid state definition for add_state: {e}")

            # Verify uniqueness
            entity = new_graph.entities[entity_id]
            if any(s.id == state_def.id for s in entity.states):
                raise PatchError(f"State ID {state_def.id!r} already exists.")

            entity.states.append(state_def)
            log_entries.append({
                "op": "add_state",
                "target": state_def.id,
                "author": author,
            })

        elif op_name == "add_xform":
            entity_id = op.get("entity")
            xform_data = op.get("xform")
            if not entity_id or not xform_data:
                raise PatchError(f"Op add_xform requires 'entity' and 'xform' dict.")
            if entity_id not in new_graph.entities:
                raise PatchError(f"Entity {entity_id!r} not found for add_xform.")

            try:
                xf_def = TransformDef.model_validate(xform_data)
            except Exception as e:
                raise PatchError(f"Invalid transform definition for add_xform: {e}")

            entity = new_graph.entities[entity_id]
            if any(x.id == xf_def.id for x in entity.transforms):
                raise PatchError(f"Transform ID {xf_def.id!r} already exists.")

            # Verify state endpoints exist
            state_ids = {s.id for s in entity.states}
            if xf_def.from_state not in state_ids:
                raise PatchError(f"Transform from_state {xf_def.from_state!r} not found.")
            if xf_def.to_state not in state_ids:
                raise PatchError(f"Transform to_state {xf_def.to_state!r} not found.")

            entity.transforms.append(xf_def)
            log_entries.append({
                "op": "add_xform",
                "target": xf_def.id,
                "author": author,
            })

        elif op_name == "add_annotation":
            ann_data = op.get("annotation")
            if not ann_data:
                raise PatchError("Op add_annotation requires 'annotation' dict.")

            try:
                ann_def = Annotation.model_validate(ann_data)
            except Exception as e:
                raise PatchError(f"Invalid annotation definition for add_annotation: {e}")

            if ann_def.id in new_graph.annotations:
                raise PatchError(f"Annotation ID {ann_def.id!r} already exists.")

            new_graph.annotations[ann_def.id] = ann_def
            log_entries.append({
                "op": "add_annotation",
                "target": ann_def.id,
                "author": author,
            })

        elif op_name == "set_attr":
            target_id = op.get("target_id")
            key = op.get("key")
            value = op.get("value")
            if not target_id or key is None:
                raise PatchError("Op set_attr requires 'target_id' and 'key'.")

            # Look up target in entities, states, transforms, or annotations
            found = False
            if target_id in new_graph.entities:
                new_graph.entities[target_id].attributes[key] = value
                found = True
            elif target_id in new_graph.annotations:
                new_graph.annotations[target_id].attributes[key] = value
                found = True
            else:
                parsed = parse_id(target_id)
                eid = parsed.get("entity")
                kind = parsed.get("kind")
                if eid and eid in new_graph.entities:
                    ent = new_graph.entities[eid]
                    if kind == "state":
                        for st in ent.states:
                            if st.id == target_id:
                                st.attributes[key] = value
                                found = True
                                break
                    elif kind == "xform":
                        for xf in ent.transforms:
                            if xf.id == target_id:
                                xf.attributes[key] = value
                                found = True
                                break

            if not found:
                raise PatchError(f"Target node {target_id!r} not found for set_attr.")

            log_entries.append({
                "op": "set_attr",
                "target": target_id,
                "key": key,
                "author": author,
            })

        elif op_name == "deprecate":
            target_id = op.get("target_id")
            if not target_id:
                raise PatchError("Op deprecate requires 'target_id'.")

            found = False
            if target_id in new_graph.annotations:
                new_graph.annotations[target_id].status = "deprecated"
                found = True
            else:
                parsed = parse_id(target_id)
                eid = parsed.get("entity")
                kind = parsed.get("kind")
                if eid and eid in new_graph.entities:
                    ent = new_graph.entities[eid]
                    if kind == "state":
                        for st in ent.states:
                            if st.id == target_id:
                                st.status = "deprecated"
                                found = True
                                break
                    elif kind == "xform":
                        for xf in ent.transforms:
                            if xf.id == target_id:
                                xf.status = "deprecated"
                                found = True
                                break

            if not found:
                raise PatchError(f"Target node {target_id!r} not found for deprecate.")

            log_entries.append({
                "op": "deprecate",
                "target": target_id,
                "author": author,
            })

        elif op_name == "add_alias":
            entity_id = op.get("entity")
            if not entity_id or entity_id not in new_graph.entities:
                raise PatchError(f"Entity {entity_id!r} not found for add_alias.")

            ent = new_graph.entities[entity_id]
            alias_str = op.get("alias")
            cue_alias_data = op.get("cue_alias")
            state_slug = op.get("state_slug")

            if alias_str:
                if alias_str not in ent.aliases:
                    ent.aliases.append(alias_str)
                log_entries.append({
                    "op": "add_alias",
                    "target": entity_id,
                    "alias": alias_str,
                    "author": author,
                })
            elif cue_alias_data and state_slug:
                try:
                    ca = CueAlias.model_validate(cue_alias_data)
                except Exception as e:
                    raise PatchError(f"Invalid cue_alias for add_alias: {e}")
                target_state = next((s for s in ent.states if s.slug == state_slug), None)
                if not target_state:
                    raise PatchError(f"State slug {state_slug!r} not found in {entity_id}")
                target_state.cue_aliases.append(ca)
                log_entries.append({
                    "op": "add_cue_alias",
                    "target": target_state.id,
                    "cue": ca.cue,
                    "author": author,
                })
            else:
                raise PatchError("Op add_alias requires either 'alias' or ('cue_alias' and 'state_slug').")

        else:
            raise PatchError(f"Unrecognized patch operation: {op_name!r}")

    new_graph.changelog.extend(log_entries)
    return new_graph
