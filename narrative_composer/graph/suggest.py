"""
Context-Specific Suggestion Engine for Narrative Node Graph (NNG).
Generates deterministic, rule-based prose and continuity recommendations
leveraging graph topology, state transitions, annotations, and world state.
"""

from typing import Any, Dict, List, Optional, Set
import re

from narrative_composer.graph.extract import RunResult
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import Suggestion
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.graph.world_port import WorldStateProvider
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType


def suggest(
    result: RunResult,
    graph: StoryGraph,
    canon: str,
    elements: List[ASTElement],
    world: Optional[WorldStateProvider] = None,
) -> List[Suggestion]:
    """
    Analyzes RunResult and AST against StoryGraph to produce actionable suggestions.
    Generates reaction_beat, callback, relationship_echo, and skipped_stage notices.
    """
    suggestions: List[Suggestion] = []
    resolver = EntityResolver(graph, canon=canon)

    # 1. Reaction Beat
    for xf in result.xforms:
        if xf.source == "explicit":
            # Find element index
            elem_idx = -1
            for idx, el in enumerate(elements):
                if el.line_number >= xf.at.line:
                    elem_idx = idx
                    break

            if elem_idx != -1:
                window = elements[elem_idx + 1 : elem_idx + 9]
                reaction_found = False

                for win_el in window:
                    if win_el.node_type == ASTNodeType.CHARACTER:
                        speaker_eid, _ = resolver.resolve_cue(win_el.content)
                        if speaker_eid and speaker_eid != xf.entity:
                            reaction_found = True
                            break
                    elif win_el.node_type == ASTNodeType.ACTION:
                        action_text = win_el.content
                        for other_eid, other_ent in graph.entities.items():
                            if other_eid != xf.entity:
                                all_names = [other_ent.display_name] + other_ent.aliases
                                if any(re.search(r"\b" + re.escape(n) + r"\b", action_text, re.IGNORECASE) for n in all_names):
                                    reaction_found = True
                                    break
                    if reaction_found:
                        break

                if not reaction_found:
                    try:
                        st_label = graph.get_state(xf.to_state).label
                    except KeyError:
                        st_label = xf.to_state
                    ctx_nodes = [xf.to_state]
                    if xf.xform_id:
                        ctx_nodes.append(xf.xform_id)
                    suggestions.append(
                        Suggestion(
                            kind="reaction_beat",
                            line=xf.at.line,
                            entity=xf.entity,
                            text=f"{xf.entity.title()} changes to {st_label} at line {xf.at.line} with no reaction from another character in the next 8 lines.",
                            context_node_ids=ctx_nodes,
                        )
                    )

    # 2. Callback Available
    for st in result.states:
        # Check active lore annotations targeting this state
        for ann in graph.annotations.values():
            if ann.status == "active" and ann.target_id == st.state_id and ann.kind == "lore":
                if canon and ann.canons and canon not in ann.canons:
                    continue
                if ann.tags:
                    elem_idx = 0
                    for idx, el in enumerate(elements):
                        if el.line_number >= st.at.line:
                            elem_idx = idx
                            break
                    window_text = " ".join(e.content for e in elements[elem_idx : elem_idx + 21])
                    tags_found = any(
                        re.search(r"\b" + re.escape(tag) + r"\b", window_text, re.IGNORECASE)
                        for tag in ann.tags
                    )
                    if not tags_found:
                        suggestions.append(
                            Suggestion(
                                kind="callback",
                                line=st.at.line,
                                entity=st.entity,
                                text=f"Callback available for {st.state_id}: '{ann.text}'. Consider integrating into dialogue.",
                                context_node_ids=[st.state_id, ann.id],
                            )
                        )

    # 3. Relationship Echo (only if world is provided)
    if world is not None:
        for st in result.states:
            rels = world.relationships(st.entity, scene_index=st.at.scene_index, canon=canon)
            for rel in rels:
                kind = rel.get("kind", "")
                if kind in ["second_in_command_of", "girlfriend"]:
                    partner = rel["b"] if rel["a"] == st.entity else rel["a"]
                    elem_idx = 0
                    for idx, el in enumerate(elements):
                        if el.line_number >= st.at.line:
                            elem_idx = idx
                            break
                    window = elements[elem_idx : elem_idx + 21]

                    # Check if partner appears in window
                    partner_mentioned = False
                    partner_spoke_directly = False
                    for win_el in window:
                        if win_el.node_type == ASTNodeType.CHARACTER:
                            spk, _ = resolver.resolve_cue(win_el.content)
                            if spk == partner:
                                partner_mentioned = True
                        elif win_el.node_type == ASTNodeType.ACTION:
                            if partner in graph.entities:
                                p_names = [graph.entities[partner].display_name] + graph.entities[partner].aliases
                                if any(re.search(r"\b" + re.escape(n) + r"\b", win_el.content, re.IGNORECASE) for n in p_names):
                                    partner_mentioned = True

                    if partner_mentioned:
                        suggestions.append(
                            Suggestion(
                                kind="relationship_echo",
                                line=st.at.line,
                                entity=st.entity,
                                text=f"Relationship echo available: {st.entity} ({kind} partner {partner}) is co-present without dialogue acknowledgment.",
                                context_node_ids=[st.state_id],
                            )
                        )

    # 4. Intermediate Showcase (skipped stages)
    for st in result.states:
        if st.source == "inferred_intermediate":
            try:
                st_def = graph.get_state(st.state_id)
                label = st_def.label
            except KeyError:
                label = st.state_id
            suggestions.append(
                Suggestion(
                    kind="skipped_stage",
                    line=st.at.line,
                    entity=st.entity,
                    text=f"Stage '{label}' ({st.state_id}) was skipped; consider showing it.",
                    context_node_ids=[st.state_id],
                )
            )

    # Deduplicate and sort deterministically
    unique_suggestions: Dict[str, Suggestion] = {}
    for s in suggestions:
        key = f"{s.line}:{s.entity}:{s.kind}:{s.text}"
        if key not in unique_suggestions:
            unique_suggestions[key] = s

    return sorted(
        unique_suggestions.values(),
        key=lambda s: (s.line or 0, s.entity or "", s.kind, s.text),
    )
