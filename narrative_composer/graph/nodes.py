"""
Core Operator Nodes for Narrative Node Graph (NNG).
Wraps text source, AST parsing, state extraction, and run graph building.
"""

from pathlib import Path
from typing import Any, Dict, List

from narrative_composer.graph.checks import run_checks
from narrative_composer.graph.discover import (
    DiscoveryResult,
    apply_discovery,
    discover,
)
from narrative_composer.graph.extract import RunResult, extract_run
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.kernel import Node
from narrative_composer.graph.models import Suggestion, Violation
from narrative_composer.graph.runbuild import build_run_graph
from narrative_composer.graph.suggest import suggest
from narrative_composer.graph.world_port import WorldStateProvider
from narrative_composer.models.ast_nodes import ASTElement
from narrative_composer.parser.fountain_lexer import FountainParser


class TextSourceNode(Node):
    """Provides raw screenplay text from parameters or file path."""
    type = "text_source"

    def external_dependencies(self):
        from narrative_composer.persistence import file_hash
        path = self.params.get('path')
        return {'file':file_hash(Path(path))} if path and self.params.get('text') is None else {}

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        text = self.params.get("text")
        if text is not None:
            return str(text)
        path_str = self.params.get("path")
        if path_str:
            p = Path(path_str)
            return p.read_text(encoding="utf-8")
        return ""


class DefinitionSourceNode(Node):
    """Explicit, serializable approved definition input; ctx remains a versioned override."""
    type = 'definition_source'

    def cook(self, ctx, inputs):
        import copy
        from narrative_composer.graph.models import EntityDef, Annotation
        from narrative_composer.graph.registry import load_registry
        if ctx.get('graph') is not None:
            return copy.deepcopy(ctx['graph'])
        payload = self.params.get('graph')
        if payload is None:
            return StoryGraph.from_registry(load_registry())
        return StoryGraph(entities={key:EntityDef.model_validate(value) for key,value in payload['entities'].items()},
            annotations={key:Annotation.model_validate(value) for key,value in payload.get('annotations',{}).items()},
            changelog=copy.deepcopy(payload.get('changelog',[])))


class ParseNode(Node):
    """Parses raw screenplay text into Fountain ASTElements."""
    type = "parse"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> List[ASTElement]:
        raw_text = inputs.get("text", "")
        return FountainParser.parse(raw_text)


class DiscoverNode(Node):
    """Autonomous character and state discovery from AST elements."""
    type = "discover"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> DiscoveryResult:
        elements: List[ASTElement] = inputs.get("ast", [])
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph")
        canon: str = self.params.get("canon", "hot_scoomp_main")
        run_id: str = self.params.get("run_id", "default_run")
        cfg: Optional[Dict[str, Any]] = self.params.get("cfg")

        return discover(elements, graph, canon=canon, run_id=run_id, cfg=cfg)


class ApplyDiscoveryNode(Node):
    """Applies DiscoveryResult patch operations to produce an updated StoryGraph."""
    type = "apply_discovery"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> StoryGraph:
        discovery_res: DiscoveryResult = inputs.get("discovery")
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph")
        if not discovery_res:
            return graph
        # Expose candidate actors without promoting discovered transition legality.
        import copy
        from narrative_composer.graph.models import EntityDef
        updated_graph = copy.deepcopy(graph)
        for candidate in discovery_res.new_entities:
            entity = EntityDef.model_validate(candidate)
            updated_graph.entities[entity.entity_id] = entity
        return updated_graph


class ExtractNode(Node):
    """Extracts state and transform instances from AST using graph definitions."""
    type = "extract"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> RunResult:
        elements: List[ASTElement] = inputs.get("ast", [])
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph under key 'graph'")
        canon: str = self.params.get("canon", "hot_scoomp_main")
        run_id: str = self.params.get("run_id", "default_run")

        return extract_run(elements, graph, canon=canon, run_id=run_id,
                           initial_states=self.params.get('initial_states'),
                           reviewed_observations=self.params.get('reviewed_observations'))


class BuildRunGraphNode(Node):
    """Assembles RunResult into a fully serialized run graph dictionary."""
    type = "build_run_graph"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        result: RunResult = inputs.get("result")
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph under key 'graph'")
        canon: str = self.params.get("canon", "hot_scoomp_main")
        run_id: str = self.params.get("run_id", "default_run")

        return build_run_graph(result, graph, run_id=run_id, canon=canon)


class CheckNode(Node):
    """Executes G1-G7 graph-driven consistency and continuity checks."""
    type = "check"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> List[Violation]:
        result: RunResult = inputs.get("result")
        elements: List[ASTElement] = inputs.get("ast", [])
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph under key 'graph'")
        canon: str = self.params.get("canon", "hot_scoomp_main")

        return run_checks(result, graph, canon=canon, elements=elements)


class SuggestNode(Node):
    """Generates context-specific prose and continuity suggestions."""
    type = "suggest"

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> List[Suggestion]:
        result: RunResult = inputs.get("result")
        elements: List[ASTElement] = inputs.get("ast", [])
        graph: StoryGraph = inputs.get("graph") or ctx.get("graph")
        world: Optional[WorldStateProvider] = inputs.get("world") or ctx.get("world")
        if not graph:
            raise KeyError("Context or inputs must contain an active StoryGraph under key 'graph'")
        canon: str = self.params.get("canon", "hot_scoomp_main")

        return suggest(result, graph, canon=canon, elements=elements, world=world)


NODE_TYPES: Dict[str, Any] = {
    'definition_source': DefinitionSourceNode,
    "text_source": TextSourceNode,
    "parse": ParseNode,
    "discover": DiscoverNode,
    "apply_discovery": ApplyDiscoveryNode,
    "extract": ExtractNode,
    "build_run_graph": BuildRunGraphNode,
    "check": CheckNode,
    "suggest": SuggestNode,
}

