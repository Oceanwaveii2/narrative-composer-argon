"""
Run Graph Builder for Narrative Node Graph (NNG).
Assembles empirical state and transform instances into a structured,
timeline-indexed execution graph.
"""

from collections import defaultdict
from typing import Any, Dict, List

from narrative_composer.graph.extract import RunResult
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import SCHEMA_VERSION


def build_run_graph(
    result: RunResult,
    graph: StoryGraph,
    run_id: str,
    canon: str,
) -> Dict[str, Any]:
    """
    Constructs a JSON-serializable Run Graph linking instances to their definition models
    and establishing temporal sequencing edges.
    """
    timeline: Dict[str, List[str]] = defaultdict(list)
    edges: List[Dict[str, str]] = []

    # Map state instances into per-entity timelines
    for st in result.states:
        timeline[st.entity].append(st.id)
        # Edge to canonical state definition
        edges.append({
            "from": st.id,
            "to": st.state_id,
            "type": "instance_of",
        })

    # Sequential timeline edges
    for eid, inst_ids in timeline.items():
        for i in range(len(inst_ids) - 1):
            edges.append({
                "from": inst_ids[i],
                "to": inst_ids[i + 1],
                "type": "next",
            })

    # Transform edges
    for xf in result.xforms:
        if xf.xform_id:
            edges.append({
                "from": xf.id,
                "to": xf.xform_id,
                "type": "instance_of",
            })

    entities_present = sorted(list(timeline.keys()))

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "canon": canon,
        "entities": entities_present,
        "state_instances": [s.model_dump() for s in result.states],
        "transform_instances": [t.model_dump() for t in result.xforms],
        "timeline": dict(timeline),
        "edges": edges,
        "unresolved_cues": result.unresolved_cues,
        "canon_leaks": result.canon_leaks,
        "observations": getattr(result, 'observations', []),
    }
