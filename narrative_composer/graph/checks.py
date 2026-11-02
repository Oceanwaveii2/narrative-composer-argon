"""
Graph-Driven Consistency, Canon, and Continuity Checks for Narrative Node Graph (NNG).
Evaluates RunResult and AST elements against StoryGraph topology to enforce
invariant transition legality, cue alignment, canon purity, and visual anchoring.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
import re

from narrative_composer.graph.discover import load_discovery_config
from narrative_composer.graph.enrich import semantic_context
from narrative_composer.graph.extract import RunResult
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.ids import parse_id, state_id
from narrative_composer.graph.models import Violation
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType


def run_checks(
    result: RunResult,
    graph: StoryGraph,
    canon: str,
    elements: List[ASTElement],
) -> List[Violation]:
    """
    Executes G1-G7 graph integrity checks on RunResult and AST.
    Returns ordered list of Violation models (ERROR, WARNING, INFO).
    """
    violations: List[Violation] = list(getattr(result, 'issues', []))
    cfg = load_discovery_config()
    ignore_cues = set(cfg.get("ignore_cues", []))
    resolver = EntityResolver(graph, canon=canon)

    # Cue text -> first line it appears on, so violations can point at a concrete block.
    cue_lines: Dict[str, int] = {}
    for element in elements:
        if element.node_type == ASTNodeType.CHARACTER:
            cue_text = element.content.strip()
            for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
                cue_text = cue_text.replace(suffix, "").strip()
            cue_lines.setdefault(cue_text.upper(), element.line_number)

    # =========================================================================
    # G1: ILLEGAL_TRANSITION (ERROR)
    # =========================================================================
    for xf in result.xforms:
        if xf.xform_id is None:
            # Pattern-detected candidate events already produce G8; they are
            # not an author-asserted illegal transition (G1).
            if xf.source == 'unverified_observation':
                continue
            ctx_summary = ""
            try:
                sc = semantic_context(graph, xf.to_state, canon=canon)
                ctx_summary = f" Target context: {sc['text'][:100]}"
            except Exception:
                pass
            violations.append(
                Violation(
                    rule_id="G1_ILLEGAL_TRANSITION",
                    severity="ERROR",
                    line=xf.at.line,
                    entity=xf.entity,
                    message=f"Illegal state transition for '{xf.entity}' from '{xf.from_state}' to '{xf.to_state}' with no valid transform edge.",
                    suggestion=f"Define a valid TransformDef connecting '{xf.from_state}' and '{xf.to_state}' or insert intermediate states.{ctx_summary}",
                )
            )

    # =========================================================================
    # G2: CUE_STATE_MISMATCH (ERROR)
    # =========================================================================
    # Track state history by line number for each entity
    # state_at_line: map entity -> list of (line, state_slug)
    history_by_entity: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    for st in result.states:
        parsed = parse_id(st.state_id)
        history_by_entity[st.entity].append((st.at.line, parsed["slug"]))

    for el in elements:
        if el.node_type == ASTNodeType.CHARACTER:
            cue_raw = el.content.strip()
            clean_cue = cue_raw
            for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
                clean_cue = clean_cue.replace(suffix, "").strip()

            eid, implied_slug = resolver.resolve_cue(clean_cue)
            if eid and implied_slug:
                # Find entity's state at this line
                history = history_by_entity.get(eid, [])
                current_state_slug = None
                for line_no, slug in history:
                    if line_no <= el.line_number:
                        current_state_slug = slug
                    else:
                        break

                if current_state_slug and current_state_slug != implied_slug:
                    violations.append(
                        Violation(
                            rule_id="G2_CUE_STATE_MISMATCH",
                            severity="ERROR",
                            line=el.line_number,
                            entity=eid,
                            message=f"Speaker cue '{cue_raw}' suggests '{implied_slug}', while the graph currently records '{current_state_slug}' for '{eid}'.",
                            suggestion="Inspect the source and state history; review the observation and any transition cause separately.",
                        )
                    )

    # =========================================================================
    # G3: CANON_LEAK (ERROR)
    # =========================================================================
    for leak in result.canon_leaks:
        parsed = re.search(r"Cue '([^']+)' belongs to entity '([^']+)'", leak)
        cue_name = parsed.group(1) if parsed else None
        leak_entity = parsed.group(2) if parsed else None
        violations.append(
            Violation(
                rule_id="G3_CANON_LEAK",
                severity="ERROR",
                line=cue_lines.get(cue_name.upper()) if cue_name else None,
                entity=leak_entity,
                message=f"Canon boundary violation: {leak}",
                suggestion=f"Remove non-canonical character references or switch the active canon from '{canon}'.",
            )
        )

    # =========================================================================
    # G4: UNEXPLAINED_REVERT (WARNING)
    # =========================================================================
    seen_states_by_entity: Dict[str, Set[str]] = defaultdict(set)
    for st in result.states:
        parsed = parse_id(st.state_id)
        slug = parsed["slug"]
        eid = st.entity
        seen_states_by_entity[eid].add(slug)

    for xf in result.xforms:
        if xf.xform_id:
            try:
                xf_def = graph.get_xform(xf.xform_id)
                to_slug = parse_id(xf.to_state)["slug"]
                from_slug = parse_id(xf.from_state)["slug"]
                # Reverting to an earlier state
                if (xf.from_state != xf_def.from_state or xf.to_state != xf_def.to_state) and not xf_def.reversible:
                    # Check if an explicit reverse transform (from_slug -> to_slug) exists
                    rev_id = f"{xf.entity}.xform.{from_slug}__{to_slug}"
                    has_explicit_reverse = False
                    try:
                        graph.get_xform(rev_id)
                        has_explicit_reverse = True
                    except KeyError:
                        pass
                    if not has_explicit_reverse:
                        violations.append(
                            Violation(
                                rule_id="G4_UNEXPLAINED_REVERT",
                                severity="WARNING",
                                line=xf.at.line,
                                entity=xf.entity,
                                message=f"Unexplained state reversion for '{xf.entity}' back to '{to_slug}' without a reversible transform definition.",
                                suggestion=f"Mark transform '{xf.xform_id}' as reversible=True or add an explicit reverse transform.",
                            )
                        )
            except KeyError:
                pass

    # =========================================================================
    # G5: ANCHOR_MISSING (INFO)
    # =========================================================================
    for st in result.states:
        if st.source in ("base", "initial"):
            continue  # Initial appearance does not require immediate anchor bursts
        try:
            st_def = graph.get_state(st.state_id)
            if st_def.visual_anchors:
                # Find matching element index
                st_idx = 0
                for idx, el in enumerate(elements):
                    if el.line_number >= st.at.line:
                        st_idx = idx
                        break

                window = elements[st_idx : st_idx + 13]
                found_anchor = False
                for win_el in window:
                    if win_el.node_type == ASTNodeType.ACTION:
                        text_lower = win_el.content.lower()
                        if any(re.search(r"\b" + re.escape(a.lower()) + r"\b", text_lower) for a in st_def.visual_anchors):
                            found_anchor = True
                            break

                if not found_anchor:
                    anchors_str = ", ".join(st_def.visual_anchors)
                    violations.append(
                        Violation(
                            rule_id="G5_ANCHOR_MISSING",
                            severity="INFO",
                            line=st.at.line,
                            entity=st.entity,
                            message=f"State '{st.state_id}' entered without expected sensory visual anchors ({anchors_str}) in subsequent action lines.",
                            suggestion=f"Ground the character's new physical state in action prose using anchors like: {', '.join(st_def.visual_anchors[:3])}.",
                        )
                    )
        except KeyError:
            pass

    # =========================================================================
    # G6: UNRESOLVED_CUE (INFO)
    # =========================================================================
    for cue in result.unresolved_cues:
        if cue.upper() not in ignore_cues:
            violations.append(
                Violation(
                    rule_id="G6_UNRESOLVED_CUE",
                    severity="INFO",
                    line=cue_lines.get(cue.upper()),
                    entity=None,
                    message=f"Unresolved speaker cue '{cue}' detected in screenplay.",
                    suggestion=f"Register '{cue}' as a character alias or allow autonomous discovery to ingest it.",
                )
            )

    # =========================================================================
    # G7: AUTO_DISCOVERED (INFO)
    # =========================================================================
    reported_nodes: Set[str] = set()
    for st in result.states:
        try:
            st_def = graph.get_state(st.state_id)
            if st_def.attributes.get("origin") == "auto" and st_def.attributes.get("provisional"):
                if st.state_id not in reported_nodes:
                    reported_nodes.add(st.state_id)
                    conf = st_def.attributes.get("confidence", 0.5)
                    evidence = st_def.attributes.get("evidence", "")
                    violations.append(
                        Violation(
                            rule_id="G7_AUTO_DISCOVERED",
                            severity="INFO",
                            line=st.at.line,
                            entity=st.entity,
                            message=f"Auto-discovered provisional state '{st.state_id}' used (confidence: {conf}). Evidence: {evidence}",
                            suggestion=f"Run '--graph-promote {st.entity}' to finalize this state into permanent catalog.",
                        )
                    )
        except KeyError:
            pass

        # Also check entity-level provisional status
        if st.entity in graph.entities:
            ent = graph.entities[st.entity]
            if ent.attributes.get("origin") == "auto" and ent.attributes.get("provisional"):
                if st.entity not in reported_nodes:
                    reported_nodes.add(st.entity)
                    conf = ent.attributes.get("confidence", 0.5)
                    evidence = ent.attributes.get("evidence", "")
                    violations.append(
                        Violation(
                            rule_id="G7_AUTO_DISCOVERED",
                            severity="INFO",
                            line=st.at.line,
                            entity=st.entity,
                            message=f"Auto-discovered provisional entity '{st.entity}' active in run (confidence: {conf}). Evidence: {evidence}",
                            suggestion=f"Run '--graph-promote {st.entity}' to promote to permanent character library.",
                        )
                    )

    return violations
