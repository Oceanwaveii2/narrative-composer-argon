"""
Automated Pipeline Execution for Narrative Node Graph (NNG).
Builds deterministic operator node networks, executes cooking, generates run artifacts,
and manages auto-discovery persistence.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import copy
import json
import re

from narrative_composer.graph.discover import (
    DiscoveryResult,
    persist_discovery,
)
from narrative_composer.graph.enrich import load_annotations
from narrative_composer.graph.extract import RunResult
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.kernel import Network
from narrative_composer.graph.models import Suggestion, Violation
from narrative_composer.graph.nodes import (
    ApplyDiscoveryNode,
    BuildRunGraphNode,
    CheckNode,
    DiscoverNode,
    DefinitionSourceNode,
    ExtractNode,
    NODE_TYPES,
    ParseNode,
    SuggestNode,
    TextSourceNode,
)
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.viewer import render_viewer
from narrative_composer.graph.world_port import PrototypeWorld, WorldStateProvider


def build_network_for_text(
    text: str,
    canon: str,
    run_id: str,
    graph: Optional[StoryGraph] = None,
    annotations_path: Optional[Union[str, Path]] = None,
    initial_states: Optional[Dict[str, str]] = None,
    reviewed_observations: Optional[List[Dict[str, Any]]] = None,
) -> Network:
    """
    Constructs an operator Network chaining:
    TextSource -> Parse -> Discover -> ApplyDiscovery -> Extract -> BuildRunGraph -> Check -> Suggest
    with deterministic operator IDs.
    """
    net = Network()
    definitions = DefinitionSourceNode('op.definitions.1', {'graph':graph.to_dict() if graph is not None else None})
    net.add(definitions)

    # 1. TextSource
    n_text = TextSourceNode("op.text_source.1", {"text": text})
    net.add(n_text)

    # 2. Parse
    n_parse = ParseNode("op.parse.1", {})
    net.add(n_parse)
    net.connect("op.text_source.1", "op.parse.1", "text")

    # 3. Discover
    n_disc = DiscoverNode("op.discover.1", {"canon": canon, "run_id": run_id})
    net.add(n_disc)
    net.connect("op.parse.1", "op.discover.1", "ast")
    net.connect('op.definitions.1', 'op.discover.1', 'graph')

    # 4. ApplyDiscovery
    n_apply = ApplyDiscoveryNode("op.apply_discovery.1", {})
    net.add(n_apply)
    net.connect("op.discover.1", "op.apply_discovery.1", "discovery")
    net.connect('op.definitions.1', 'op.apply_discovery.1', 'graph')

    # 5. Extract
    n_ext = ExtractNode("op.extract.1", {"canon": canon, "run_id": run_id,
        'initial_states':initial_states or {}, 'reviewed_observations':reviewed_observations or []})
    net.add(n_ext)
    net.connect("op.parse.1", "op.extract.1", "ast")
    net.connect("op.apply_discovery.1", "op.extract.1", "graph")

    # 6. BuildRunGraph
    n_bld = BuildRunGraphNode("op.build_run_graph.1", {"canon": canon, "run_id": run_id})
    net.add(n_bld)
    net.connect("op.extract.1", "op.build_run_graph.1", "result")
    net.connect("op.apply_discovery.1", "op.build_run_graph.1", "graph")

    # 7. Check
    n_chk = CheckNode("op.check.1", {"canon": canon})
    net.add(n_chk)
    net.connect("op.extract.1", "op.check.1", "result")
    net.connect("op.parse.1", "op.check.1", "ast")
    net.connect("op.apply_discovery.1", "op.check.1", "graph")

    # 8. Suggest
    n_sug = SuggestNode("op.suggest.1", {"canon": canon})
    net.add(n_sug)
    net.connect("op.extract.1", "op.suggest.1", "result")
    net.connect("op.parse.1", "op.suggest.1", "ast")
    net.connect("op.apply_discovery.1", "op.suggest.1", "graph")

    return net


def cook_network_to_report(
    net: Network,
    canon: str,
    run_id: str,
    ctx: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], StoryGraph, Optional[DiscoveryResult]]:
    """
    Evaluates operator network up to run graph, checks, and suggestions,
    returning (run_graph, report_dict, updated_graph, discovery_result).
    """
    run_graph: Dict[str, Any] = net.cook("op.build_run_graph.1", ctx=ctx)
    violations: List[Violation] = net.cook("op.check.1", ctx=ctx)
    suggestions: List[Suggestion] = net.cook("op.suggest.1", ctx=ctx)

    discovery_res: Optional[DiscoveryResult] = net._cache.get("op.discover.1")
    updated_graph: StoryGraph = net._cache.get("op.apply_discovery.1", ctx.get("graph"))

    total_state_instances = len(run_graph.get("state_instances", []))
    total_transforms = len(run_graph.get("transform_instances", []))

    from narrative_composer.graph.diagnostics import present_diagnostic
    displayed = [present_diagnostic(dict(v.model_dump(), source='graph')) for v in violations]
    error_count = sum(1 for v in displayed if v['severity'] == "ERROR")
    warning_count = sum(1 for v in displayed if v['severity'] == "WARNING")
    info_count = sum(1 for v in displayed if v['severity'] == "INFO")

    summary = {
        "state_instances": total_state_instances,
        "transforms": total_transforms,
        "errors": error_count,
        "warnings": warning_count,
        "infos": info_count,
        "review_questions": sum(1 for v in displayed if v.get('requires_author_review')),
        "gate_errors": sum(1 for v in violations if v.severity == 'ERROR'),
        "suggestions": len(suggestions),
    }

    discoveries_data = {
        "entities": [
            {
                "entity_id": e["entity_id"],
                "display_name": e.get("display_name"),
                "confidence": e.get("attributes", {}).get("confidence"),
                "evidence": e.get("attributes", {}).get("evidence"),
                "line": e.get("attributes", {}).get("first_seen_line"),
            }
            for e in (discovery_res.new_entities if discovery_res else [])
        ],
        "states": [
            {
                "id": s_entry["state"]["id"],
                "entity": s_entry["entity"],
                "slug": s_entry["state"]["slug"],
                "confidence": s_entry["state"].get("attributes", {}).get("confidence"),
                "evidence": s_entry["state"].get("attributes", {}).get("evidence"),
                "line": s_entry["state"].get("attributes", {}).get("discovered_at_line"),
            }
            for s_entry in (discovery_res.new_states if discovery_res else [])
        ],
        "transforms": [
            {
                "id": xf_entry["xform"]["id"],
                "from_state": xf_entry["xform"]["from_state"],
                "to_state": xf_entry["xform"]["to_state"],
            }
            for xf_entry in (discovery_res.new_xforms if discovery_res else [])
        ],
    }

    report_dict = {
        "run_id": run_id,
        "canon": canon,
        "summary": summary,
        "discoveries": discoveries_data,
        "violations": displayed,
        "suggestions": [s.model_dump() for s in suggestions],
    }

    return run_graph, report_dict, updated_graph, discovery_res


def process_text(
    text: str,
    canon: str,
    run_id: str,
    out_dir: Union[str, Path],
    graph: Optional[StoryGraph] = None,
    world: Optional[WorldStateProvider] = None,
    learn: bool = True,
    annotations_path: Optional[Union[str, Path]] = None,
    initial_states: Optional[Dict[str, str]] = None,
    reviewed_observations: Optional[List[Dict[str, Any]]] = None,
    data_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Executes the full automated Narrative Node Graph pipeline from screenplay text:
    1. Loads registry and annotations if graph not provided.
    2. Builds operator node network.
    3. Cooks the network and evaluates run graph, checks, and suggestions.
    4. Persists discoveries if learn=True.
    5. Writes <run_id>.chain.json, <run_id>.graph.json, <run_id>.report.json.
    6. Returns the report dictionary.
    """
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        raise ValueError('Run ID must contain only letters, digits, underscores and hyphens')
    out_path = Path(out_dir).resolve()
    targets = [out_path / f'{run_id}.{suffix}' for suffix in ('chain.json','graph.json','report.json','viewer.html')]
    if any(path.exists() for path in targets):
        raise FileExistsError('Graph output already exists; choose a new run ID or output folder')

    if graph is None:
        graph = StoryGraph.from_registry(load_registry())

    if annotations_path is not None:
        ann_path = Path(annotations_path)
        if ann_path.exists():
            graph = load_annotations(graph, ann_path)

    working_graph = copy.deepcopy(graph)
    net = build_network_for_text(
        text=text,
        canon=canon,
        run_id=run_id,
        graph=working_graph,
        annotations_path=annotations_path,
        initial_states=initial_states,
        reviewed_observations=reviewed_observations,
    )

    ctx = {"graph": working_graph, "world": world}
    run_graph, report_dict, updated_graph, discovery_res = cook_network_to_report(
        net=net,
        canon=canon,
        run_id=run_id,
        ctx=ctx,
    )

    if learn and discovery_res:
        persist_discovery(discovery_res, updated_graph)

    out_path.mkdir(parents=True, exist_ok=True)

    chain_file = out_path / f"{run_id}.chain.json"
    graph_file = out_path / f"{run_id}.graph.json"
    report_file = out_path / f"{run_id}.report.json"

    for path, value in ((chain_file, net.to_dict()), (graph_file, run_graph), (report_file, report_dict)):
        with path.open('x', encoding='utf-8') as output:
            output.write(json.dumps(value, indent=2, sort_keys=True))

    viewer_file = out_path / f"{run_id}.viewer.html"
    render_viewer(
        run_graph=run_graph,
        report=report_dict,
        out_path=viewer_file,
        graph=updated_graph,
        data_root=data_root,
    )

    return report_dict
