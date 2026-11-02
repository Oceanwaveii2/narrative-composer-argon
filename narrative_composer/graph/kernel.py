"""
Operator Node Kernel for Narrative Node Graph (NNG).
Minimal Houdini-style procedural cooking engine with dirty-flag caching,
topological sorting, cycle detection, and serializable networks.
"""

from typing import Any, Dict, List, Optional, Set, Type
import hashlib
import json

from narrative_composer.graph.models import SCHEMA_VERSION


class Node:
    """Base class for all operator nodes in an NNG network."""
    type: str = "base"

    def __init__(self, node_id: str, params: Optional[Dict[str, Any]] = None):
        self.node_id: str = node_id
        self.params: Dict[str, Any] = params or {}
        self.inputs: Dict[str, str] = {}  # port_name -> upstream_node_id

    def cook(self, ctx: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
        """Computes node output from evaluated upstream inputs."""
        raise NotImplementedError

    def external_dependencies(self) -> Dict[str, Any]:
        return {}


class Network:
    """Procedural DAG operator network with dirty-flag dependency tracking."""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self._cache: Dict[str, Any] = {}
        self._hash_cache: Dict[str, str] = {}
        self._dirty: Set[str] = set()

    def add(self, node: Node) -> Node:
        """Adds a node to the network and marks it dirty."""
        if node.node_id in self.nodes:
            raise ValueError(f'Duplicate operator: {node.node_id}')
        self.nodes[node.node_id] = node
        self._dirty.add(node.node_id)
        return node

    def connect(self, upstream_id: str, downstream_id: str, port: str = "default") -> None:
        """Connects an upstream node's output to a downstream node's input port."""
        if upstream_id not in self.nodes:
            raise KeyError(f"Upstream node not found: {upstream_id!r}")
        if downstream_id not in self.nodes:
            raise KeyError(f"Downstream node not found: {downstream_id!r}")

        self.nodes[downstream_id].inputs[port] = upstream_id
        self._mark_downstream_dirty(downstream_id)

    def _get_dependents(self, node_id: str) -> List[str]:
        """Finds all direct downstream nodes that consume node_id as an input."""
        return [
            nid for nid, node in self.nodes.items()
            if node_id in node.inputs.values()
        ]

    def _mark_downstream_dirty(self, node_id: str) -> None:
        """Recursively marks a node and all its transitive consumers as dirty."""
        queue = [node_id]
        while queue:
            curr = queue.pop()
            self._dirty.add(curr)
            for dep in self._get_dependents(curr):
                if dep not in self._dirty:
                    queue.append(dep)

    def set_param(self, node_id: str, key: str, value: Any) -> None:
        """Updates a node parameter and flags the node and all downstream nodes dirty."""
        if node_id not in self.nodes:
            raise KeyError(f"Node not found: {node_id!r}")
        self.nodes[node_id].params[key] = value
        self._mark_downstream_dirty(node_id)

    def topo_order(self, target: str) -> List[str]:
        """
        Computes topological execution order of nodes needed to evaluate target.
        Raises ValueError if a cycle is detected.
        """
        if target not in self.nodes:
            raise KeyError(f"Target node not found: {target!r}")

        order: List[str] = []
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def dfs(curr: str):
            if curr in visiting:
                raise ValueError(f"Cycle detected in network involving node: {curr!r}")
            if curr in visited:
                return

            visiting.add(curr)
            curr_node = self.nodes[curr]
            # Visit all upstream input dependencies
            for port in sorted(curr_node.inputs.keys()):
                upstream_id = curr_node.inputs[port]
                if upstream_id not in self.nodes:
                    raise KeyError(f"Missing upstream dependency: {upstream_id!r}")
                dfs(upstream_id)

            visiting.remove(curr)
            visited.add(curr)
            order.append(curr)

        dfs(target)
        return order

    def cook(self, target: str, ctx: Optional[Dict[str, Any]] = None) -> Any:
        """
        Cooks the network up to target node, evaluating only dirty or uncomputed nodes.
        Returns the evaluation result of target node.
        """
        eval_ctx = ctx or {}
        order = self.topo_order(target)

        for nid in order:
            node = self.nodes[nid]

            # Compute fingerprint hash of inputs and params
            upstream_hashes = {
                port: self._hash_cache.get(up_id, "")
                for port, up_id in node.inputs.items()
            }
            hash_payload = {
                "type": node.type,
                "params": node.params,
                "upstreams": upstream_hashes,
                'external_dependencies': node.external_dependencies(),
                "context": {key: (value.to_dict() if hasattr(value, 'to_dict') else
                                   value.model_dump() if hasattr(value, 'model_dump') else value)
                            for key, value in eval_ctx.items()},
            }
            node_hash = hashlib.sha256(
                json.dumps(hash_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()

            needs_cook = (
                nid in self._dirty
                or nid not in self._cache
                or self._hash_cache.get(nid) != node_hash
            )

            if needs_cook:
                evaluated_inputs = {
                    port: self._cache[up_id]
                    for port, up_id in node.inputs.items()
                }
                result = node.cook(eval_ctx, evaluated_inputs)
                self._cache[nid] = result
                self._hash_cache[nid] = node_hash
                self._dirty.discard(nid)

        return self._cache[target]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the operator network topology and node parameters."""
        nodes_data = []
        for nid in sorted(self.nodes.keys()):
            node = self.nodes[nid]
            nodes_data.append({
                "id": node.node_id,
                "type": node.type,
                "params": node.params,
                "inputs": node.inputs,
            })
        return {
            "schema_version": SCHEMA_VERSION,
            "nodes": nodes_data,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], node_types: Dict[str, Type[Node]]
    ) -> "Network":
        """Reconstructs a network from dictionary and registered node type classes."""
        net = cls()
        nodes_data = data.get("nodes", [])

        # Pass 1: create nodes
        for nd in nodes_data:
            nid = nd["id"]
            ntype = nd["type"]
            params = nd.get("params", {})
            if ntype not in node_types:
                raise KeyError(f"Unregistered node type: {ntype!r}")
            node_cls = node_types[ntype]
            node = node_cls(nid, params=params)
            node.inputs = nd.get("inputs", {})
            net.nodes[nid] = node
            net._dirty.add(nid)

        return net
