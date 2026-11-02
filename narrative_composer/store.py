"""
Unified story node store.

The system previously had four disconnected models: Fountain text (Document blocks),
character definitions (EntityDef JSON), the epistemic/spatial manifest, and two separate
diagnostic reporters. They met only at line numbers.

This module projects all of them into one graph of typed nodes and edges:

    scene:<slug>          has_block        blk:<id>
    blk:<id>              speaks_as        ent:<entity_id>
    blk:<id>              realizes         st:<entity.state.slug>
    ent:<id>              has_state        st:...
    st:...                reaches          st:...        (via transforms)
    ent:<id>              has_transform    xf:<id>
    fact:<id>, prop:<id>, beat:<id>        manifest nodes, with beat dependencies

Everything is a node with an ID and data. `to_text()` and `entity_definition()` project a
subset back to their native formats, so the store is the source of truth and the formats
become views. Diagnostics are stored once, against node IDs, regardless of which checker
produced them.

Editing:
    set_block_text(store, block_id, "new line")   -> changes text projection
    to_text(store)                                -> lossless screenplay
    entity_definition(store, "stella")            -> EntityDef-compatible dict
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from narrative_composer.compiler.document import Block, BlockRole, Document, parse_document, rebuild_scenes
from narrative_composer.compiler.identity import (
    entries_from_document,
    load_entries,
    IdentitySidecarError,
    sidecar_path,
    stabilize,
)
from narrative_composer.graph.extract import extract_run
from narrative_composer.graph.models import EntityDef, StateDef, TransformDef
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.resolver import EntityResolver
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.models.epistemic import EpistemicBelief, EpistemicMatrix, NarrativeFact
from narrative_composer.models.spatial_fsm import PhysicalEntity, SpatialGraph
from narrative_composer.parser.fountain_lexer import FountainParser

SCHEMA_VERSION = 1
DEFAULT_SCREENPLAY = Path(__file__).resolve().parent.parent / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "hot_scoomp_manifest.json"


@dataclass
class Node:
    id: str
    kind: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    type: str
    src: str
    dst: str
    data: Dict[str, Any] = field(default_factory=dict)


class NodeStore:
    """A single graph of story nodes. Every subsystem is a projection of this."""

    def __init__(self, meta: Optional[Dict[str, Any]] = None) -> None:
        self.meta: Dict[str, Any] = meta or {}
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []

    # -- construction ---------------------------------------------------------
    def add_node(self, node_id: str, kind: str, **data: Any) -> Node:
        if node_id in self.nodes:
            raise ValueError(f'Duplicate node ID: {node_id}')
        node = Node(id=node_id, kind=kind, data=data)
        self.nodes[node_id] = node
        return node

    def add_edge(self, edge_type: str, src: str, dst: str, **data: Any) -> None:
        if src not in self.nodes or dst not in self.nodes:
            raise ValueError(f'Missing edge endpoint: {src} -> {dst}')
        self.edges.append(Edge(type=edge_type, src=src, dst=dst, data=data))

    # -- access ---------------------------------------------------------------
    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def of_kind(self, kind: str) -> List[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def outgoing(self, node_id: str, edge_type: Optional[str] = None) -> List[Edge]:
        return [
            e for e in self.edges
            if e.src == node_id and (edge_type is None or e.type == edge_type)
        ]

    def incoming(self, node_id: str, edge_type: Optional[str] = None) -> List[Edge]:
        return [
            e for e in self.edges
            if e.dst == node_id and (edge_type is None or e.type == edge_type)
        ]

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "meta": copy.deepcopy(self.meta),
            "nodes": [
                {"id": n.id, "kind": n.kind, "data": copy.deepcopy(n.data)}
                for n in sorted(self.nodes.values(), key=lambda n: n.id)
            ],
            "edges": [
                {"type": e.type, "src": e.src, "dst": e.dst, "data": copy.deepcopy(e.data)}
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NodeStore":
        store = cls(meta=copy.deepcopy(payload.get("meta", {})))
        for raw in payload.get("nodes", []):
            store.add_node(raw['id'], raw['kind'], **copy.deepcopy(raw.get('data', {})))
        for raw in payload.get("edges", []):
            store.add_edge(raw['type'], raw['src'], raw['dst'], **copy.deepcopy(raw.get('data', {})))
        return store

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "NodeStore":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# -----------------------------------------------------------------------------
# Projections out of the store
# -----------------------------------------------------------------------------

def to_text(store: NodeStore) -> str:
    """Rebuilds the screenplay from block nodes, lossless for untouched blocks."""
    lines: List[str] = list(store.meta.get("source_lines", []))
    for node in store.of_kind("block"):
        index = node.data["line"] - 1
        if 0 <= index < len(lines):
            lines[index] = node.data.get("raw", node.data.get("text", lines[index]))
    return "\n".join(lines)


def document_from_store(store: NodeStore) -> Document:
    """Render exactly the IDs and spans the editor and diagnostics address."""
    blocks = [Block(id=n.id.removeprefix('blk:'), role=BlockRole(n.data['role']),
                    text=n.data['text'], raw=n.data['raw'], line=n.data['line'],
                    speaker=n.data.get('speaker'), start=n.data.get('start', 0),
                    end=n.data.get('end', len(n.data['raw'])))
              for n in sorted(store.of_kind('block'), key=lambda n: (n.data['line'], n.data.get('ordinal', 0)))]
    doc = Document(blocks, list(store.meta['source_lines']))
    rebuild_scenes(doc)
    return doc


def entity_definition(store: NodeStore, entity_id: str) -> Dict[str, Any]:
    """Projects one entity back to the character-definition format."""
    entity = store.node(f"ent:{entity_id}")
    def with_port(node):
        data = copy.deepcopy(node.data)
        ports = store.outgoing(node.id, 'has_data_port')
        if ports:
            data['data_port'] = copy.deepcopy(store.node(ports[0].dst).data)
        return data
    states = [
        with_port(store.node(edge.dst))
        for edge in store.outgoing(f"ent:{entity_id}", "has_state")
    ]
    transforms = [
        store.node(edge.dst).data
        for edge in store.outgoing(f"ent:{entity_id}", "has_transform")
    ]
    states.sort(key=lambda s: (s.get("order", 0), s.get("slug", "")))
    payload = with_port(entity)
    payload.update(states=copy.deepcopy(states), transforms=copy.deepcopy(transforms))
    return payload


def set_block_text(store: NodeStore, block_id: str, new_text: str) -> None:
    """Edits one block node; the text projection and the raw line follow."""
    if "\n" in new_text or "\r" in new_text:
        raise ValueError("A block edit must be a single line")
    node = store.node(block_id)
    if node.kind != "block":
        raise ValueError(f"{block_id!r} is not a block node")

    raw = node.data['raw']
    start, end = node.data.get('start', 0), node.data.get('end', len(raw))
    updated = raw[:start] + new_text + raw[end:]
    delta = len(new_text) - (end - start)
    for sibling in store.of_kind('block'):
        if sibling.data['line'] != node.data['line']:
            continue
        sibling.data['raw'] = updated
        if sibling.id == node.id:
            sibling.data['end'] = start + len(new_text)
        elif sibling.data.get('start', 0) >= end:
            sibling.data['start'] += delta
            sibling.data['end'] += delta
    node.data["text"] = new_text
    store.meta['source_lines'][node.data['line'] - 1] = updated
    store.meta['id_map'] = entries_from_document(document_from_store(store))


# -----------------------------------------------------------------------------
# Building the store
# -----------------------------------------------------------------------------

def _load_manifest(manifest_path: Path) -> Dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _manifest_models(manifest: Dict[str, Any]):
    facts = {k: NarrativeFact(**v) for k, v in manifest.get("facts", {}).items()}
    epistemic = EpistemicMatrix(facts=facts)
    for character, beliefs in manifest.get("initial_beliefs", {}).items():
        for fact_id, value in beliefs.items():
            epistemic.set_belief(character, fact_id, EpistemicBelief(value))
    props = {k: PhysicalEntity(**v) for k, v in manifest.get("props", {}).items()}
    spatial = SpatialGraph(
        items=props,
        character_locations=manifest.get("character_locations", {}),
        room_topology=manifest.get("room_topology", {}),
    )
    return epistemic, spatial


def _add_document_nodes(store: NodeStore, document: Document) -> None:
    for ordinal, block in enumerate(document.blocks):
        store.add_node(f'blk:{block.id}', 'block', role=block.role.value, text=block.text,
                       raw=block.raw, line=block.line, speaker=block.speaker,
                       start=block.start, end=block.end, ordinal=ordinal)
    for scene in document.scenes:
        scene_id = f"scene:{scene.id}"
        store.add_node(scene_id, "scene", title=scene.id)
        if scene.heading is not None:
            store.add_edge("has_block", scene_id, f"blk:{scene.heading.id}")
        for block in scene.blocks:
            if block.role == BlockRole.SCENE_HEADING:
                continue
            store.add_edge("has_block", scene_id, f"blk:{block.id}")

def _add_registry_nodes(store: NodeStore, graph: StoryGraph) -> None:
    def add_port(owner, port):
        port_node = 'port:' + port.id
        store.add_node(port_node, 'data_port', **port.model_dump())
        store.add_edge('has_data_port', owner, port_node)
        for binding in port.bindings:
            reference = binding.model_dump()
            key = hashlib.sha256(json.dumps(reference, sort_keys=True).encode('utf-8')).hexdigest()
            dataset_node = 'dataset:' + key
            if dataset_node not in store.nodes:
                store.add_node(dataset_node, 'dataset', **reference)
            store.add_edge('binds_dataset', port_node, dataset_node, domain=binding.domain)
        return port_node

    for entity_id, entity in graph.entities.items():
        ent_node = f"ent:{entity_id}"
        store.add_node(ent_node, 'entity', **entity.model_dump(exclude={'states', 'transforms', 'data_port'}))
        port_node = add_port(ent_node, entity.data_port)

        for state in entity.states:
            st_node = f"st:{state.id}"
            store.add_node(st_node, 'state', **state.model_dump(exclude={'data_port'}))
            state_port = add_port(st_node, state.data_port)
            if state.data_port.mode in ('inherit', 'extend', 'override'):
                store.add_edge('inherits_data_from', state_port, port_node, mode=state.data_port.mode)
            store.add_edge("has_state", ent_node, st_node)

        for xform in entity.transforms:
            xf_node = f"xf:{xform.id}"
            store.add_node(xf_node, 'transform', **xform.model_dump())
            store.add_edge("has_transform", ent_node, xf_node)

            from_node, to_node = f"st:{xform.from_state}", f"st:{xform.to_state}"
            store.add_edge("reaches", from_node, to_node, via=xform.id)


def _add_manifest_nodes(store: NodeStore, manifest: Dict[str, Any]) -> None:
    """Manifest entries become nodes holding their full model dump, so edits round-trip."""
    for fact_id, fact in manifest.get("facts", {}).items():
        data = copy.deepcopy(fact)
        data.setdefault("fact_id", fact_id)
        store.add_node(f"fact:{fact_id}", "fact", **data)

    for prop_id, prop in manifest.get("props", {}).items():
        data = copy.deepcopy(prop)
        data.setdefault("item_id", prop_id)
        store.add_node(f"prop:{prop_id}", "prop", **data)

    for beat_id, beat in manifest.get("beats", {}).items():
        data = copy.deepcopy(beat)
        data.setdefault("beat_id", beat_id)
        store.add_node(f"beat:{beat_id}", "beat", **data)
    for beat_id, beat in manifest.get('beats', {}).items():
        for prereq in beat.get("prerequisite_beat_ids", []) or []:
            store.add_edge("depends_on", f"beat:{beat_id}", f"beat:{prereq}")


def _add_attachments(
    store: NodeStore,
    document: Document,
    graph: StoryGraph,
    canon: str,
    run: Any,
) -> None:
    """Connects text nodes to story nodes: who speaks a block, which state it realizes."""
    blocks_by_line: Dict[int, List[str]] = {}
    for block in document.blocks:
        blocks_by_line.setdefault(block.line, []).append(f"blk:{block.id}")

    resolver = EntityResolver(graph, canon=canon)
    for block in document.blocks:
        if block.role != BlockRole.CUE or not block.speaker:
            continue
        entity_id, state_slug = resolver.resolve_cue(block.speaker)
        if entity_id:
            store.add_edge("speaks_as", f"blk:{block.id}", f"ent:{entity_id}", cue=block.speaker)
            if state_slug:
                state_node = f"st:{entity_id}.state.{state_slug}"
                store.add_edge("speaks_as", f"blk:{block.id}", state_node, cue=block.speaker)

    for instance in run.states:
        for block_id in blocks_by_line.get(instance.at.line, []):
            if f"st:{instance.state_id}" in store.nodes:
                store.add_edge(
                    "realizes",
                    block_id,
                    f"st:{instance.state_id}",
                    source=instance.source,
                )


def _add_diagnostics(
    store: NodeStore,
    graph: StoryGraph,
    canon: str,
    epistemic: EpistemicMatrix,
    spatial: SpatialGraph,
    elements: List[Any],
    run: Any,
) -> None:
    """One diagnostic stream: both checkers, addressed by node ID."""
    blocks_by_line: Dict[int, List[str]] = {}
    for node in store.of_kind("block"):
        blocks_by_line.setdefault(node.data["line"], []).append(node.id)

    diagnostics: List[Dict[str, Any]] = []

    for violation in ScreenplayLinter(epistemic, spatial).lint_full_script(elements):
        candidates = blocks_by_line.get(violation.line_number, [])
        diagnostics.append(
            {
                "source": "linter",
                "rule_id": violation.rule_id,
                "severity": violation.severity,
                "node_id": candidates[0] if candidates else None,
                "line": violation.line_number,
                "message": violation.diagnostic_message,
                "suggestion": violation.repair_instruction,
            }
        )

    from narrative_composer.graph.checks import run_checks

    for violation in run_checks(run, graph, canon=canon, elements=elements):
        node_id = None
        if violation.line is not None:
            candidates = blocks_by_line.get(violation.line, [])
            node_id = candidates[0] if candidates else None
        elif violation.entity and f"ent:{violation.entity}" in store.nodes:
            node_id = f"ent:{violation.entity}"
        diagnostics.append(
            {
                "source": "graph",
                "rule_id": violation.rule_id,
                "severity": violation.severity,
                "node_id": node_id,
                "line": violation.line,
                "message": violation.message,
                "suggestion": violation.suggestion,
            }
        )

    store.meta["diagnostics"] = diagnostics


def registry_from_store(store: NodeStore) -> Dict[str, EntityDef]:
    """
    Rebuilds character definitions from the store's entity nodes.

    This is what lets in-session edits affect diagnostics: the checker runs against the
    edited store rather than re-reading JSON from disk.
    """
    registry: Dict[str, EntityDef] = {}
    for entity_node in store.of_kind("entity"):
        entity_id = entity_node.data.get("entity_id")
        registry[entity_id] = EntityDef.model_validate(entity_definition(store, entity_id))
    return registry


def manifest_payload(store: NodeStore, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Projects fact/prop/beat nodes back onto a manifest document."""
    payload = copy.deepcopy(manifest)
    for node in store.of_kind("fact"):
        fact_id = node.data.get("fact_id")
        if fact_id:
            payload.setdefault("facts", {})[fact_id] = copy.deepcopy(node.data)
    for node in store.of_kind("prop"):
        prop_id = node.data.get("item_id")
        if prop_id:
            payload.setdefault("props", {})[prop_id] = copy.deepcopy(node.data)
    for node in store.of_kind("beat"):
        beat_id = node.data.get("beat_id")
        if beat_id:
            payload.setdefault("beats", {})[beat_id] = copy.deepcopy(node.data)
    return payload


_BUILD_CACHE: "OrderedDict[str, NodeStore]" = OrderedDict()
_CACHE_SIZE = 4


def _registry_fingerprint(registry: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for entity_id in sorted(registry):
        digest.update(entity_id.encode("utf-8"))
        digest.update(registry[entity_id].model_dump_json().encode("utf-8"))
    return digest.hexdigest()


def clear_build_cache() -> None:
    """Drops cached stores (tests, or after editing config on disk)."""
    _BUILD_CACHE.clear()


def build_store(
    script_path: Path = DEFAULT_SCREENPLAY,
    manifest_path: Path = DEFAULT_MANIFEST,
    canon: str = "hot_scoomp_main",
    registry: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
    use_cache: bool = True,
    manifest: Optional[Dict[str, Any]] = None,
    previous_entries: Optional[List[Dict[str, Any]]] = None,
    allow_unverified_identity_reconciliation: bool = False,
) -> NodeStore:
    """
    Projects text, character definitions, manifest, and diagnostics into one store.

    Builds are cached by (text, registry, manifest, canon); a cache hit returns an
    independent copy, so callers may mutate the result freely. Pass `text` to build from
    an in-memory buffer, and `registry` to build from edited character definitions.
    """
    if text is None:
        text = Path(script_path).read_bytes().decode('utf-8')
    manifest_bytes = (json.dumps(manifest, sort_keys=True).encode('utf-8') if manifest is not None
                      else Path(manifest_path).read_bytes())
    registry = registry if registry is not None else load_registry()
    loaded_sidecar = False
    if previous_entries is None and script_path is not None:
        identity_path = sidecar_path(script_path)
        loaded_sidecar = identity_path.exists()
        previous_entries = load_entries(identity_path)

    if loaded_sidecar:
        # Legacy lists have no source hash. Verify them against the disk source
        # before a warm-cache return can hide a partial map or external edit.
        from collections import Counter
        try:
            disk_text = Path(script_path).read_bytes().decode('utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            raise IdentitySidecarError('Cannot compare identity sidecar with its source; preserve both files') from exc
        baseline_document = parse_document(disk_text)
        recorded = Counter((item['role'], item['text'], item.get('line')) for item in previous_entries)
        observed = Counter((block.role.value, block.text, block.line) for block in baseline_document.blocks)
        if recorded != observed and not allow_unverified_identity_reconciliation:
            raise IdentitySidecarError('Identity sidecar does not match the opened story. Preserve both files and follow IDENTITY_RECOVERY.md before restoring a matched backup.')

    cache_key = None
    if use_cache:
        digest = hashlib.sha256()
        digest.update(str(Path(script_path).resolve()).encode('utf-8'))
        digest.update(str(Path(manifest_path).resolve()).encode('utf-8'))
        digest.update(json.dumps(previous_entries, sort_keys=True).encode('utf-8'))
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(manifest_bytes)
        digest.update(b"\x00")
        digest.update(canon.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(_registry_fingerprint(registry).encode("ascii"))
        cache_key = digest.hexdigest()
        cached = _BUILD_CACHE.get(cache_key)
        if cached is not None:
            _BUILD_CACHE.move_to_end(cache_key)
            return NodeStore.from_dict(cached.to_dict())

    manifest = json.loads(manifest_bytes.decode("utf-8"))
    epistemic, spatial = _manifest_models(manifest)

    elements = FountainParser.parse(text)
    document = parse_document(text, elements=elements)

    id_entries = stabilize(document, previous_entries)

    graph = StoryGraph.from_registry(registry)
    store = NodeStore(
        meta={
            "canon": canon,
            "source": str(script_path),
            "manifest": str(manifest_path),
            "source_lines": text.split("\n"),
            "id_map": id_entries,
            "manifest_payload": copy.deepcopy(manifest),
        }
    )

    _add_document_nodes(store, document)
    _add_registry_nodes(store, graph)
    _add_manifest_nodes(store, manifest)

    run = extract_run(elements, graph, canon=canon, run_id="store",
                      initial_states=manifest.get('initial_character_states'),
                      reviewed_observations=manifest.get('reviewed_state_observations'))
    _add_attachments(store, document, graph, canon, run)
    _add_diagnostics(store, graph, canon, epistemic, spatial, elements, run)
    from narrative_composer.graph.runbuild import build_run_graph
    store.meta['run_graph'] = build_run_graph(run, graph, run_id='workspace', canon=canon)
    from narrative_composer.persistence import file_hash
    store.meta['expected_files'] = {str(Path(p).resolve()): file_hash(Path(p))
                                    for p in (script_path, manifest_path, sidecar_path(script_path))}
    store.meta['revision'] = hashlib.sha256(json.dumps({
        'text': text, 'registry': _registry_fingerprint(registry), 'manifest': manifest,
        'identities': id_entries, 'canon': canon,
    }, sort_keys=True).encode('utf-8')).hexdigest()
    store.meta['coverage'] = {key: 'modeled' if manifest.get(key) else 'not modeled'
                              for key in ('facts', 'props', 'beats', 'initial_beliefs')}

    if cache_key is not None:
        _BUILD_CACHE[cache_key] = NodeStore.from_dict(store.to_dict())
        while len(_BUILD_CACHE) > _CACHE_SIZE:
            _BUILD_CACHE.popitem(last=False)
    return store


def summary(store: NodeStore) -> Dict[str, Any]:
    kinds: Dict[str, int] = {}
    for node in store.nodes.values():
        kinds[node.kind] = kinds.get(node.kind, 0) + 1
    diagnostics = store.meta.get("diagnostics", [])
    return {
        "nodes": len(store.nodes),
        "edges": len(store.edges),
        "kinds": dict(sorted(kinds.items())),
        "diagnostics": len(diagnostics),
        "errors": sum(1 for d in diagnostics if d["severity"] == "ERROR"),
        "addressed": sum(1 for d in diagnostics if d.get("node_id")),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="narrative_composer.store", description="Unified story node store")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Project text + registry + manifest into one node store")
    build.add_argument("--script", default=str(DEFAULT_SCREENPLAY))
    build.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    build.add_argument("--canon", default="hot_scoomp_main")
    build.add_argument("--out", default="out/nodes.json")

    diagnose = sub.add_parser("diagnose", help="Print the store's unified diagnostics")
    diagnose.add_argument("store")
    diagnose.add_argument("--severity", default=None, help="Filter by severity (ERROR/WARNING/INFO)")

    export_text = sub.add_parser("export-text", help="Project the store back to screenplay text")
    export_text.add_argument("store")
    export_text.add_argument("--out", default=None)

    export_entity = sub.add_parser("export-entity", help="Project one entity back to character JSON")
    export_entity.add_argument("store")
    export_entity.add_argument("entity")
    export_entity.add_argument("--out", default=None)

    args = parser.parse_args(argv)

    if args.command == "build":
        store = build_store(Path(args.script), Path(args.manifest), canon=args.canon)
        path = store.save(Path(args.out))
        info = summary(store)
        print(f"store: {path}")
        print(f"nodes: {info['nodes']:,}  edges: {info['edges']:,}")
        print(f"kinds: {info['kinds']}")
        print(f"diagnostics: {info['diagnostics']} ({info['errors']} errors, {info['addressed']} addressed to a node)")
        return 0

    store = NodeStore.load(Path(args.store))

    if args.command == "diagnose":
        for diagnostic in store.meta.get("diagnostics", []):
            if args.severity and diagnostic["severity"] != args.severity:
                continue
            print(
                f"[{diagnostic['severity']:7}] {diagnostic['rule_id']:34} "
                f"{diagnostic['node_id'] or '(store)':28} {diagnostic['message'][:70]}"
            )
        return 0

    if args.command == "export-text":
        text = to_text(store)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out} ({len(text):,} chars)")
        else:
            sys.stdout.write(text)
        return 0

    if args.command == "export-entity":
        payload = entity_definition(store, args.entity)
        rendered = json.dumps(payload, indent=2)
        if args.out:
            Path(args.out).write_text(rendered, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(rendered)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
