"""
Semantic Context Enrichment for Narrative Node Graph (NNG).
Attaches lore, visual cues, and external annotations to graph nodes,
synthesizing compact, prioritized prompt-ready semantic context.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import json

from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.ids import parse_id
from narrative_composer.graph.models import Annotation
from narrative_composer.graph.patch import apply_patch


def attach(graph: StoryGraph, annotation: Annotation) -> None:
    """Attaches a single Annotation to StoryGraph via atomic patch operation."""
    updated = apply_patch(
        graph,
        [{"op": "add_annotation", "annotation": annotation.model_dump()}],
        author="enrich",
    )
    graph.annotations.update(updated.annotations)
    if updated.changelog:
        graph.changelog.append(updated.changelog[-1])


def load_annotations(graph: StoryGraph, path: Path) -> int:
    """
    Loads external annotations from a JSON file (list or dict with 'annotations' key).
    Skips annotations whose IDs already exist in the graph.
    Returns count of newly attached annotations.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return 0

    raw = json.loads(p.read_text(encoding="utf-8"))
    ann_list = raw if isinstance(raw, list) else raw.get("annotations", [])

    ops = []
    added_count = 0
    seen_ids = set(graph.annotations.keys())
    for item in ann_list:
        try:
            ann = Annotation.model_validate(item)
            if ann.id not in seen_ids:
                seen_ids.add(ann.id)
                ops.append({"op": "add_annotation", "annotation": ann.model_dump()})
                added_count += 1
        except Exception:
            continue

    if ops:
        updated = apply_patch(graph, ops, author="load_annotations")
        graph.annotations.update(updated.annotations)
        graph.changelog.extend(updated.changelog[-len(ops):])

    return added_count


def semantic_context(
    graph: StoryGraph,
    target_id: str,
    canon: Optional[str] = None,
    depth: int = 1,
    max_chars: int = 1200,
) -> Dict[str, Any]:
    """
    Assembles prioritized semantic context, neighbors, and external lore for a target node.
    Returns structured context dictionary and length-bounded text summary.
    """
    label: str = target_id
    attributes: Dict[str, Any] = {}
    previous_states: List[str] = []
    next_states: List[str] = []
    target_annotations: List[Annotation] = []
    neighbor_annotations: List[Annotation] = []

    # 1. Inspect Target Node Identity
    if target_id in graph.entities:
        ent = graph.entities[target_id]
        label = ent.display_name
        attributes = dict(ent.attributes)
    else:
        try:
            parsed = parse_id(target_id)
            kind = parsed.get("kind")
            if kind == "state":
                st = graph.get_state(target_id)
                label = st.label
                attributes = dict(st.attributes)

                # Identify previous and next states via active transforms
                eid = parsed.get("entity")
                if eid and eid in graph.entities:
                    for xf in graph.entities[eid].transforms:
                        if xf.status != "active":
                            continue
                        if canon and xf.canons and canon not in xf.canons:
                            continue
                        if xf.to_state == target_id and xf.from_state not in previous_states:
                            previous_states.append(xf.from_state)
                        if xf.from_state == target_id and xf.to_state not in next_states:
                            next_states.append(xf.to_state)

            elif kind == "xform":
                xf = graph.get_xform(target_id)
                label = f"Transition: {xf.from_state} -> {xf.to_state}"
                attributes = dict(xf.attributes)
        except Exception:
            label = target_id

    # 2. Collect Matching Direct Annotations (active, canon-compatible, sorted by confidence)
    for ann in graph.annotations.values():
        if ann.status != "active":
            continue
        if canon and ann.canons and canon not in ann.canons:
            continue

        if ann.target_id == target_id:
            target_annotations.append(ann)
        elif target_id in graph.entities and ann.target_id.startswith(f"{target_id}.state."):
            # Secondary priority: state annotations attached when querying parent entity
            target_annotations.append(ann)
        elif ann.target_id in previous_states or ann.target_id in next_states:
            neighbor_annotations.append(ann)

    target_annotations.sort(key=lambda a: a.confidence, reverse=True)
    neighbor_annotations.sort(key=lambda a: a.confidence, reverse=True)

    # 3. Construct Plain-Text Summary (bounded by max_chars)
    lines: List[str] = [f"[{label.upper()}]"]

    # Visual anchors or attributes if present
    anchors = attributes.get("visual_anchors")
    if anchors:
        lines.append(f"Visual Anchors: {', '.join(anchors)}")

    for ann in target_annotations:
        bullet = f"- ({ann.kind.upper()} | {ann.source}): {ann.text.strip()}"
        lines.append(bullet)

    if depth >= 1 and neighbor_annotations:
        lines.append("Adjacent Context:")
        for nann in neighbor_annotations[:3]:
            lines.append(f"  * [Adjacent {nann.target_id}] {nann.text.strip()}")

    full_text = "\n".join(lines)
    if len(full_text) > max_chars:
        full_text = full_text[: max_chars - 3].rstrip() + "..."

    return {
        "target": target_id,
        "label": label,
        "attributes": attributes,
        "annotations": [a.model_dump() for a in target_annotations],
        "neighbors": {
            "previous": previous_states,
            "next": next_states,
        },
        "neighbor_annotations": [na.model_dump() for na in neighbor_annotations],
        "text": full_text,
    }
