"""
Local live-preview editor, backed by the unified node store.

    python -m narrative_composer.editor [--file SCREENPLAY] [--manifest MANIFEST] [--port 8765]

The store is the model: text, character definitions, and the manifest are projections of
one node graph. The editor renders the preview from the Document projection, edits any node
by ID (block text or JSON node data), shows one diagnostic stream addressed by node ID, and
on save writes the text projection, edited character definitions, and a nodes.json snapshot.

Loopback only. Standard library only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from difflib import SequenceMatcher
import copy
import hashlib
import json
import re
import sqlite3
import time
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from dataclasses import replace
from narrative_composer.compiler.reader_renderer import GENERIC_THEME
from narrative_composer.workspace import project_report, ReactionRule, present_diagnostic

from narrative_composer.compiler.document import parse_document, replace_block_text
from narrative_composer.compiler.identity import save_entries, sidecar_path
from narrative_composer.compiler.reader_renderer import HOT_SCOOMP_THEME, render_reader
from narrative_composer.compiler.selective_recook import plan_patches
from narrative_composer.graph.models import EntityDef
from narrative_composer.graph.models import StateDef, TransformDef
from narrative_composer.graph.data_ports import DataPort
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry
from narrative_composer.persistence import (COMMIT_LOCK, WorkspaceConflict, commit_files, file_hash,
                                            recover_transactions, workspace_read_snapshot)
from narrative_composer.rich_document import (load_document as load_rich_document,
    sidecar_content as rich_sidecar_content, sidecar_path as rich_sidecar_path,
    validate_document as validate_rich_document)
from narrative_composer.models.causal_dag import StoryBeatNode
from narrative_composer.models.epistemic import NarrativeFact
from narrative_composer.models.spatial_fsm import PhysicalEntity
from narrative_composer.store import (
    NodeStore,
    build_store,
    entity_definition,
    manifest_payload,
    registry_from_store,
    set_block_text,
    summary,
    to_text,
    document_from_store,
)

MAX_BODY_BYTES = 8 * 1024 * 1024
SESSION_LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENPLAY = ROOT / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
DEFAULT_MANIFEST = ROOT / "hot_scoomp_manifest.json"
DEFAULT_ENTITY_DIR = ROOT / "narrative_composer" / "config" / "graph" / "characters"
DEFAULT_NODES_OUT = ROOT / "out" / "nodes.json"


def snapshot_path(screenplay_path: Path) -> Path:
    """Each story owns its own saved graph and decision-history sidecar."""
    path = Path(screenplay_path)
    return path.with_suffix(path.suffix + '.nodes.json')


def timeline_sections(index_path: Path):
    """Read only registered story/manifest paths below the timeline workspace."""
    root = Path(index_path).resolve().parent
    index = json.loads(Path(index_path).read_text(encoding='utf-8'))
    sections = index.get('sections')
    if not isinstance(sections, list):
        raise ValueError('Invalid timeline index')
    result, seen = [], set()
    for section in sections:
        if not isinstance(section, dict) or any(not isinstance(section.get(k), str)
                                                for k in ('id','story','manifest','canon')):
            raise ValueError('Invalid timeline section')
        if section['id'] in seen:
            raise ValueError('Duplicate timeline section')
        seen.add(section['id'])
        story, manifest = (root/section['story']).resolve(), (root/section['manifest']).resolve()
        if not story.is_relative_to(root) or not manifest.is_relative_to(root) or not story.is_file() or not manifest.is_file():
            raise ValueError('Timeline section must refer to existing workspace files')
        result.append({'id':section['id'],'story':story,'manifest':manifest,'canon':section['canon'],
                       'status':section.get('status','source section')})
    return result


def restore_browser_newlines(original: str, edited: str) -> str:
    """Reapply original line endings after a browser textarea normalizes them."""
    pieces = re.split(r'(\r\n|\r|\n)', original)
    old_lines, endings = pieces[::2], pieces[1::2] + ['']
    new_lines = edited.split('\n')
    if new_lines == old_lines:
        return original
    counts = Counter(e for e in endings if e)
    default = counts.most_common(1)[0][0] if counts else '\n'
    new_endings = [default] * len(new_lines)
    for tag,i1,i2,j1,j2 in SequenceMatcher(a=old_lines,b=new_lines,autojunk=False).get_opcodes():
        if tag == 'equal':
            for offset in range(j2-j1):
                new_endings[j1+offset] = endings[i1+offset] or default
        elif tag == 'replace':
            for offset in range(j2-j1):
                if i1+offset < i2 and endings[i1+offset]:
                    new_endings[j1+offset] = endings[i1+offset]
        elif tag == 'insert' and i1:
            nearby = endings[i1-1] or default
            for index in range(j1,j2):
                new_endings[index] = nearby
    new_endings[-1] = ''
    return ''.join(line+ending for line,ending in zip(new_lines,new_endings))


# -----------------------------------------------------------------------------
# Model helpers
# -----------------------------------------------------------------------------

def render_source(text: str) -> str:
    """Renders Fountain source to standalone reader HTML."""
    return render_reader(parse_document(text), HOT_SCOOMP_THEME)


def document_stats(text: str) -> Dict[str, Any]:
    document = parse_document(text)
    words = sum(len(block.text.split()) for block in document.blocks)
    return {
        "blocks": len(document.blocks),
        "scenes": len(document.scenes),
        "words": words,
        "characters": len(text),
    }


def block_info(text: str, block_id: str) -> Dict[str, Any]:
    document = parse_document(text)
    block = document.block_by_id(block_id)
    return {"id": block.id, "role": block.role.value, "line": block.line, "text": block.text}


def update_block_text(text: str, block_id: str, new_display: str) -> str:
    """Rewrites one block's text into the source (document-layer primitive)."""
    return replace_block_text(text, block_id, new_display)


def build_editor_store(
    text: str,
    screenplay_path: Path,
    manifest_path: Path,
    registry: Optional[Dict[str, Any]] = None,
) -> NodeStore:
    return build_store(
        script_path=Path(screenplay_path),
        manifest_path=Path(manifest_path),
        text=text,
        registry=registry,
    )


def node_payload(store: NodeStore, node_id: str) -> Dict[str, Any]:
    node = store.node(node_id)
    return {"id": node.id, "kind": node.kind, "data": node.data}


def introduced_errors(before: NodeStore, after: NodeStore):
    """Keep pre-existing diagnostics visible while blocking new proposal errors."""
    def key(item):
        return (item['source'],item['rule_id'],item.get('line'),item['message'])
    existing = Counter(key(d) for d in before.meta['diagnostics'] if d['severity']=='ERROR')
    added = []
    for diagnostic in after.meta['diagnostics']:
        if diagnostic['severity'] != 'ERROR':
            continue
        identity = key(diagnostic)
        if existing[identity]:
            existing[identity] -= 1
        else:
            added.append(diagnostic)
    return added


def entity_for_node(store: NodeStore, node_id: str) -> Optional[str]:
    node = store.node(node_id)
    if node.kind == "entity":
        return node.data.get("entity_id")
    if node.kind == 'data_port':
        owners = store.incoming(node_id, 'has_data_port')
        return entity_for_node(store, owners[0].src) if owners else None
    for edge in store.incoming(node_id, "has_state") + store.incoming(node_id, "has_transform"):
        return store.node(edge.src).data.get("entity_id")
    return None


def carry_dirty_edits(previous: Optional[NodeStore], store: NodeStore) -> NodeStore:
    """
    Re-applies edited node data onto a freshly built store.

    Rebuilding reads character JSON and the manifest from disk, which would discard
    in-session edits. Every dirty node (entity/state/transform/fact/prop/beat) is carried
    over so the rebuilt store reflects what the user has been editing.
    """
    if previous is None:
        return store

    dirty_nodes = list(previous.meta.get("dirty_nodes", []))
    for node_id in dirty_nodes:
        if node_id in previous.nodes and node_id in store.nodes:
            store.nodes[node_id].data = copy.deepcopy(previous.nodes[node_id].data)

    store.meta["dirty_nodes"] = dirty_nodes
    store.meta["dirty_entities"] = sorted(set(previous.meta.get("dirty_entities", [])))
    return store


def apply_node_edit(store: NodeStore, node_id: str, value: str) -> Optional[str]:
    """
    Applies an edit to one node.

    Blocks take plain text and return the new screenplay text; every other node takes a
    JSON object and returns None (the text projection is unchanged).
    """
    node = store.node(node_id)

    if node.kind == "block":
        set_block_text(store, node_id, value)
        return to_text(store)
    if node.kind in ('scene', 'dataset'):
        raise ValueError('This node is derived; edit the source or its connected port instead')

    try:
        data = json.loads(value)
    except ValueError as exc:
        raise ValueError(f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        raise ValueError("node data must be a JSON object")
    if node.kind in ('entity', 'state') and 'data_port' in data:
        raise ValueError('Edit the connected data port node instead of embedding it here')

    for key in ("id", "entity_id", "fact_id", "item_id", "beat_id", "slug"):
        if key in node.data and data.get(key) != node.data[key]:
            raise ValueError(f"{key} is immutable")
    model = {'state': StateDef, 'transform': TransformDef, 'fact': NarrativeFact,
             'prop': PhysicalEntity, 'beat': StoryBeatNode, 'data_port': DataPort}.get(node.kind)
    if model:
        model.model_validate(data)
    # Validate a copy; rejected edits must not poison the live session.
    candidate = NodeStore.from_dict(store.to_dict())
    candidate.node(node_id).data = data
    if node.kind in ('entity', 'state', 'transform', 'data_port'):
        registry = registry_from_store(candidate)
        errors = StoryGraph.from_registry(registry).validate()
        if errors:
            raise ValueError('; '.join(errors))
        for actor in registry.values():
            for rule in actor.attributes.get('behavior_rules', []):
                ReactionRule.model_validate(rule)
    node.data = copy.deepcopy(data)

    dirty_nodes = set(store.meta.get("dirty_nodes", []))
    dirty_nodes.add(node_id)
    store.meta["dirty_nodes"] = sorted(dirty_nodes)

    entity_id = entity_for_node(store, node_id)
    if entity_id:
        dirty = set(store.meta.get("dirty_entities", []))
        dirty.add(entity_id)
        store.meta["dirty_entities"] = sorted(dirty)
    return None


def save_source(path: Path, text: str) -> None:
    """Atomically writes the screenplay, keeping one .bak of the previous version."""
    path = Path(path)
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _validate_manifest(payload: Dict[str, Any]) -> None:
    """Refuses to write a manifest whose entries would not reload."""
    for fact in payload.get("facts", {}).values():
        NarrativeFact(**fact)
    for prop in payload.get("props", {}).values():
        PhysicalEntity(**prop)
    for beat in payload.get("beats", {}).values():
        StoryBeatNode(**beat)


def _dump_like(payload: Dict[str, Any], original_text: str) -> str:
    """Serialises JSON using the original file's indentation and trailing newline."""
    indent = 2
    for line in original_text.splitlines():
        stripped = line.lstrip(" ")
        if stripped and len(line) != len(stripped):
            indent = len(line) - len(stripped)
            break
    trailing = "\n" if original_text.endswith("\n") else ""
    return json.dumps(payload, indent=indent, ensure_ascii=False) + trailing


def save_workspace(
    store: NodeStore,
    text: str,
    screenplay_path: Path,
    entity_dir: Path = DEFAULT_ENTITY_DIR,
    nodes_out: Optional[Path] = DEFAULT_NODES_OUT,
    manifest_path: Optional[Path] = None,
    rich_document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Writes the text projection, edited character definitions, and a node snapshot."""
    screenplay_path = Path(screenplay_path).resolve()
    updates = {screenplay_path: text.encode('utf-8')}
    def stage(path, content):
        path = Path(path).resolve()
        if path.is_file():
            updates[path.with_suffix(path.suffix + '.bak')] = path.read_bytes()
        updates[path] = content.encode('utf-8')
    if screenplay_path.is_file():
        updates[screenplay_path.with_suffix(screenplay_path.suffix + '.bak')] = screenplay_path.read_bytes()

    rich_path = rich_sidecar_path(screenplay_path)
    if rich_document is not None:
        stage(rich_path, rich_sidecar_content(rich_document, text))
    elif rich_path.exists():
        raise WorkspaceConflict('This story has rich formatting; save it through the document editor')

    written_entities = []
    for entity_id in sorted(set(store.meta.get("dirty_entities", []))):
        payload = entity_definition(store, entity_id)
        EntityDef.model_validate(payload)  # refuse to write a definition that will not reload
        path = Path(store.meta.get('entity_paths', {}).get(entity_id, Path(entity_dir) / f'{entity_id}.json'))
        stage(path, json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
        written_entities.append(path.name)

    manifest_written = None
    dirty_nodes = set(store.meta.get("dirty_nodes", []))
    manifest_kinds = ("fact:", "prop:", "beat:")
    if manifest_path and (store.meta.get('manifest_dirty') or any(node_id.startswith(manifest_kinds) for node_id in dirty_nodes)):
        manifest_path = Path(manifest_path)
        original_text = manifest_path.read_text(encoding="utf-8")
        payload = manifest_payload(store, store.meta.get('manifest_payload') or json.loads(original_text))
        _validate_manifest(payload)
        rendered = _dump_like(payload, original_text)
        if rendered != original_text:  # never rewrite for formatting alone
            stage(manifest_path, rendered)
            manifest_written = manifest_path.name

    ids_written = None
    id_entries = store.meta.get("id_map") or []
    if id_entries:
        ids_path = sidecar_path(screenplay_path)
        stage(ids_path, json.dumps(id_entries, indent=2) + '\n')
        ids_written = ids_path.name

    snapshot = NodeStore.from_dict(store.to_dict())
    snapshot.meta['dirty_entities'] = []
    snapshot.meta['dirty_nodes'] = []
    snapshot.meta['manifest_dirty'] = False
    if nodes_out:
        stage(Path(nodes_out), json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    targets = {str(p.resolve()) for p in updates}
    expected = {p: digest for p, digest in store.meta.get('expected_files', {}).items()
                if p in targets or (Path(p).parent == Path(entity_dir).resolve())}
    for path in updates:
        expected.setdefault(str(path), file_hash(path))
    commit_files(updates, expected, screenplay_path.with_suffix(screenplay_path.suffix + '.revisions'),
                 shared_paths=[Path(entity_dir)])
    store.meta['dirty_entities'] = []
    store.meta['dirty_nodes'] = []
    store.meta['manifest_dirty'] = False
    store.meta['expected_files'] = {
        p: hashlib.sha256(updates[Path(p)].encode('utf-8') if isinstance(updates[Path(p)], str)
                          else updates[Path(p)]).hexdigest() if Path(p) in updates else digest
        for p, digest in expected.items()}

    return {
        "screenplay": screenplay_path.name,
        "entities": written_entities,
        "manifest": manifest_written,
        "ids": ids_written,
        "nodes": str(nodes_out) if nodes_out else None,
        "rich_document": rich_path.name if rich_document is not None else None,
    }


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

from narrative_composer.editor_ui import PAGE


@contextmanager
def provider_work_without_commit_lock():
    """Provider work uses a frozen snapshot; other editor requests can proceed."""
    COMMIT_LOCK.release()
    try:
        yield
    finally:
        COMMIT_LOCK.acquire()


@contextmanager
def guard_identical_provider_request(server, route, source, payload):
    """Called under COMMIT_LOCK; admit at most one live proposal job."""
    key = hashlib.sha256(json.dumps([route, str(source), {k:v for k,v in payload.items() if k != 'request_id'}], sort_keys=True,
                                  ensure_ascii=False).encode('utf-8')).hexdigest()
    if not hasattr(server, 'inflight_provider_requests'):
        server.inflight_provider_requests = set()
    if key in server.inflight_provider_requests:
        raise WorkspaceConflict('This same proposal request is already running; check its result and history before retrying')
    provider = payload.get('provider') or getattr(server, 'default_provider', 'deepseek')
    if provider != 'mock' and server.inflight_provider_requests:
        raise WorkspaceConflict(
            'Another provider proposal is already running in this editor; '
            'wait for its result before starting a new one'
        )
    server.inflight_provider_requests.add(key)
    try:
        yield
    finally:
        server.inflight_provider_requests.discard(key)


def current_rewrite_violations(change, store):
    """Recheck persisted neural proposals using the current mechanical gate."""
    if change.get('rule_id') != 'PROSE_CONDITIONING' and change.get('tier') != 'tier_2_prose_rewrite':
        return []
    from narrative_composer.condition import _lost_subject
    from narrative_composer.prose.models import ProseRewriteRequest, SpanCategory
    from narrative_composer.prose.validation import context_fields, validate_rewrite
    request = ProseRewriteRequest(request_id='proposal-review', project_id='workspace',
        document_id='story', base_revision=1, target_span_id=change['block_id'],
        original_text=change['original'], category=SpanCategory.STAGE_ACTION,
        **context_fields(store.meta['manifest_payload']))
    _, violations, _ = validate_rewrite(change['proposed'], request)
    if _lost_subject(change['original'], change['proposed']):
        violations.append('subject may have changed')
    return violations


class EditorHandler(BaseHTTPRequestHandler):
    server_version = "NarrativeComposerEditor/3.0"

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Dict[str, Any], status: int = 200) -> None:
        if getattr(self.server, 'store', None) is not None:
            payload = dict(payload, revision=self.server.store.meta['revision'])
        self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def _codex_session(self):
        from narrative_composer.codex_app_session import CodexAppSession
        with SESSION_LOCK:
            if not hasattr(self.server, 'codex_session'):
                workspace = getattr(self.server, 'timeline_path', None) or self.server.screenplay_path
                identity = hashlib.sha256(str(Path(workspace).resolve()).encode('utf-8')).hexdigest()
                directory = Path(getattr(self.server, 'codex_state_dir', ROOT / 'out' / 'codex_sessions'))
                self.server.codex_session = CodexAppSession(directory / (identity + '.json'))
            return self.server.codex_session

    def _provider(self, name):
        # Automated repairs must not accumulate in persistent chat histories.
        if name == 'gemini_session':
            from narrative_composer.gemini_session import GeminiSessionProvider
            return GeminiSessionProvider(self._gemini_session())
        from narrative_composer.prose.providers import create_prose_provider
        return create_prose_provider(name)

    def _deepseek_session(self):
        from narrative_composer.deepseek_session import DeepSeekSession
        with SESSION_LOCK:
            if not hasattr(self.server, 'deepseek_sessions'):
                self.server.deepseek_sessions = {}
            identity = hashlib.sha256(str(Path(self.server.screenplay_path).resolve()).encode('utf-8')).hexdigest()
            if identity not in self.server.deepseek_sessions:
                directory = Path(getattr(self.server, 'deepseek_state_dir', ROOT / 'out' / 'deepseek_sessions'))
                self.server.deepseek_sessions[identity] = DeepSeekSession(directory / (identity + '.json'))
            return self.server.deepseek_sessions[identity]

    def _gemini_session(self):
        from narrative_composer.gemini_session import GeminiCliSession
        with SESSION_LOCK:
            if not hasattr(self.server, 'gemini_sessions'):
                self.server.gemini_sessions = {}
            identity = hashlib.sha256(str(Path(self.server.screenplay_path).resolve()).encode('utf-8')).hexdigest()
            if identity not in self.server.gemini_sessions:
                directory = Path(getattr(self.server, 'gemini_state_dir', ROOT / 'out' / 'gemini_sessions'))
                self.server.gemini_sessions[identity] = GeminiCliSession(directory / (identity + '.json'))
            return self.server.gemini_sessions[identity]

    def _writing_session(self, kind):
        if kind == 'codex':
            return self._codex_session()
        if kind == 'deepseek':
            return self._deepseek_session()
        if kind == 'gemini':
            return self._gemini_session()
        raise ValueError('Unknown writing session')

    def _store_for(self, text: str) -> NodeStore:
        server = self.server
        if getattr(server, "store", None) is None or server.store_text != text:
            previous = getattr(server, "store", None)
            registry = (registry_from_store(previous) if previous is not None else
                        load_registry(Path(getattr(server, 'entity_dir', DEFAULT_ENTITY_DIR))))
            rebuilt = build_store(Path(server.screenplay_path), Path(server.manifest_path),
                text=text, registry=registry, canon=getattr(server, 'canon', 'hot_scoomp_main'),
                manifest=manifest_payload(previous, previous.meta['manifest_payload']) if previous else None,
                previous_entries=previous.meta['id_map'] if previous else None, use_cache=False)
            if previous:
                for key in ('dirty_nodes', 'dirty_entities', 'expected_files', 'entity_paths', 'decisions', 'manifest_dirty'):
                    rebuilt.meta[key] = copy.deepcopy(previous.meta.get(key, {} if key in ('expected_files', 'entity_paths') else []))
            else:
                entity_dir = Path(getattr(server, 'entity_dir', DEFAULT_ENTITY_DIR))
                paths = list(entity_dir.glob('*.json')) + list((entity_dir / 'auto').glob('*.json'))
                rebuilt.meta['entity_paths'] = {}
                for path in paths:
                    eid = EntityDef.model_validate_json(path.read_text(encoding='utf-8')).entity_id
                    rebuilt.meta['entity_paths'][eid] = str(path.resolve())
                    rebuilt.meta['expected_files'][str(path.resolve())] = file_hash(path)
                saved_snapshot = snapshot_path(Path(server.screenplay_path)).resolve()
                rebuilt.meta['expected_files'][str(saved_snapshot)] = file_hash(saved_snapshot)
                rich_path = rich_sidecar_path(Path(server.screenplay_path)).resolve()
                rebuilt.meta['expected_files'][str(rich_path)] = file_hash(rich_path)
                if saved_snapshot.exists():
                    try:
                        saved_meta = json.loads(saved_snapshot.read_text(encoding='utf-8')).get('meta', {})
                        if saved_meta.get('revision') == rebuilt.meta['revision']:
                            rebuilt.meta['decisions'] = saved_meta.get('decisions', [])
                            rebuilt.meta['decision_history_status'] = 'loaded'
                        else:
                            rebuilt.meta['decision_history_status'] = 'stale'
                    except (ValueError, OSError, AttributeError):
                        rebuilt.meta['decision_history_status'] = 'unreadable'
            server.store = rebuilt
            server.store_text = text
        return server.store

    def _read_payload(self) -> Optional[Dict[str, Any]]:
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > MAX_BODY_BYTES:
            self._json({"error": "payload too large"}, 413)
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("latin-1", errors="replace")
        try:
            value = json.loads(decoded)
            if not isinstance(value, dict):
                raise ValueError('Expected JSON object')
            return value
        except ValueError:
            self._json({"error": "invalid JSON"}, 400)
            return None

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            provider = getattr(self.server, 'default_provider', 'deepseek')
            page = PAGE.replace(f'<option value="{provider}">', f'<option value="{provider}" selected>', 1)
            self._send(page.encode("utf-8"), "text/html; charset=utf-8")
        elif route == '/assets/tiptap-engine.js':
            asset = Path(__file__).resolve().parent / 'assets' / 'tiptap-engine.js'
            if not asset.is_file():
                self._json({'error': 'Tiptap bundle is missing; build the frontend first'}, 404)
            else:
                self._send(asset.read_bytes(), 'application/javascript; charset=utf-8')
        elif route == "/api/source":
            story = Path(self.server.screenplay_path).resolve()
            entity_dir = Path(getattr(self.server, 'entity_dir', DEFAULT_ENTITY_DIR)).resolve()
            try:
                with workspace_read_snapshot(story.with_suffix(story.suffix + '.revisions'), [entity_dir]):
                    if urlparse(self.path).query == 'reload=1':
                        self.server.store = None
                        self.server.store_text = None
                    text = (to_text(self.server.store) if getattr(self.server, 'store', None) is not None else
                            Path(self.server.screenplay_path).read_bytes().decode('utf-8'))
                    store = self._store_for(text)
                    rich_document, rich_status = load_rich_document(Path(self.server.screenplay_path), text)
                    self.server.rich_baseline = validate_rich_document(rich_document, text)
                    dirty = bool(store.meta.get('dirty_nodes') or store.meta.get('manifest_dirty') or
                                 text != Path(self.server.screenplay_path).read_bytes().decode('utf-8'))
            except WorkspaceConflict as exc:
                self._json({'error': str(exc)}, 409)
                return
            self._json({'text': text, 'path': str(self.server.screenplay_path), 'stats': document_stats(text),
                        'rich_document': rich_document, 'rich_status': rich_status, 'dirty': dirty})
        elif route == '/api/timeline':
            path = getattr(self.server, 'timeline_path', None)
            if path is None:
                self._json({'error':'No timeline workspace'},404)
                return
            try:
                sections = timeline_sections(path)
                current = Path(self.server.screenplay_path).resolve()
                self._json({'sections':[{'id':s['id'],'status':s['status']} for s in sections],
                            'current':next((s['id'] for s in sections if s['story']==current),None)})
            except (ValueError, OSError) as exc:
                self._json({'error':str(exc)},400)
        elif route == '/api/codex/chat':
            self._json(self._codex_session().snapshot())
        elif route == '/api/deepseek/chat':
            try:
                self._json(self._deepseek_session().snapshot())
            except Exception:
                self._json({'error': 'Saved DeepSeek session cannot be loaded; preserve it and open a separate session'}, 400)
        elif route == '/api/gemini/chat':
            try:
                self._json(self._gemini_session().snapshot())
            except Exception:
                self._json({'error': 'Saved Gemini session cannot be loaded; preserve it and open a separate session'}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get('Origin') not in (None, f"http://{self.headers.get('Host')}"):
            self._json({'error':'Cross-origin workspace request rejected'}, 403)
            return
        with COMMIT_LOCK:
            self._post()

    def _post(self) -> None:
        route = urlparse(self.path).path
        payload = self._read_payload()
        if payload is None:
            return

        text = payload.get("text", "")

        try:
            previous = getattr(self.server, 'store', None)
            if previous is not None and payload.get('revision') != previous.meta['revision']:
                raise WorkspaceConflict('Stale workspace revision; refresh before applying this action')
            if previous is not None and payload.get('browser_text') is True:
                text = restore_browser_newlines(to_text(previous), text)
            rich_document = payload.get('rich_document')
            rich_revision = validate_rich_document(rich_document, text) if rich_document is not None else None
            request_id = payload.get('request_id')
            if route in ('/api/recook', '/api/condition', '/api/compose') and request_id is not None:
                from narrative_composer.proposal_store import ProposalStore
                if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id):
                    raise ValueError('Invalid proposal request ID')
                fingerprint = hashlib.sha256(json.dumps([route, str(Path(self.server.screenplay_path).resolve()),
                    {k:v for k,v in payload.items() if k != 'request_id'}], sort_keys=True,
                    ensure_ascii=False).encode('utf-8')).hexdigest()
                # Admission precedes the durable claim, so a busy request is retryable.
                with guard_identical_provider_request(
                    self.server, route, Path(self.server.screenplay_path).resolve(), payload,
                ):
                    replay = ProposalStore(self.server.screenplay_path).claim_request(request_id, fingerprint)
                if replay is not None:
                    self._json(replay)
                    return
            if route == '/api/timeline/open':
                timeline = getattr(self.server, 'timeline_path', None)
                if timeline is None:
                    raise ValueError('No timeline workspace')
                if previous is not None and (previous.meta.get('dirty_nodes') or previous.meta.get('manifest_dirty') or
                    text != Path(self.server.screenplay_path).read_bytes().decode('utf-8')):
                    raise WorkspaceConflict('Save the current draft before switching timeline sections')
                if rich_revision is not None and rich_revision != getattr(self.server, 'rich_baseline', rich_revision):
                    raise WorkspaceConflict('Save the current formatting before switching timeline sections')
                selected = next((s for s in timeline_sections(timeline) if s['id']==payload.get('id')),None)
                if not selected:
                    raise ValueError('Unknown timeline section')
                recover_transactions(selected['story'].with_suffix(selected['story'].suffix + '.revisions'),
                                     [Path(self.server.entity_dir)])
                self.server.screenplay_path = selected['story']
                self.server.manifest_path = selected['manifest']
                self.server.canon = selected['canon']
                self.server.store = None
                self.server.store_text = None
                self.server.pending_changes = {}
                self.server.reaction_cache = {}
                self.server.rich_baseline = None
                self._json({'ok':True,'section':selected['id']})
                return
            if route == "/api/render":
                started = time.perf_counter()
                store = self._store_for(text)
                theme = replace(GENERIC_THEME, page_title=Path(self.server.screenplay_path).stem,
                    verified_note='Draft · review diagnostics', graph_href='#', hero_h1_html='Story preview',
                    hero_paragraph='Formatted from the current editor revision.', compact=True)
                rendered = render_reader(document_from_store(store), theme)
                elapsed = round((time.perf_counter() - started) * 1000, 1)
                self._json({"html": rendered, "stats": document_stats(text), "ms": elapsed})
                return

            if route == "/api/nodes":
                store = self._store_for(text)
                info = summary(store)
                diagnostics = [present_diagnostic(item) for item in store.meta.get("diagnostics", [])]
                self._json({"summary": info, "diagnostics": diagnostics, "kinds": info["kinds"],
                    'nodes': [node_payload(store, node.id) for node in store.nodes.values() if node.kind != 'block'],
                    'canon':store.meta['canon'], 'coverage': store.meta['coverage'], 'observations':store.meta['run_graph']['observations']})
                return

            if route == '/api/project':
                store = self._store_for(text)
                if not hasattr(self.server, 'reaction_cache'):
                    self.server.reaction_cache = {}
                self._json(project_report(store, payload.get('event', 'challenge'), self.server.reaction_cache,
                                          payload.get('state_overrides')))
                return

            if route == '/api/cast/candidates':
                from narrative_composer.cast_candidates import discover_cast
                store = self._store_for(text)
                candidates = discover_cast(store, text)
                self._json({'candidates': [{k:v for k,v in item.items() if k != 'candidate'} for item in candidates],
                            'notice': 'Heuristic candidates are capped and require author review.'})
                return

            if route == '/api/cast/add':
                from narrative_composer.cast_candidates import discover_cast
                if payload.get('reviewed') is not True:
                    raise ValueError('Review the source and explicitly confirm the character first')
                store = self._store_for(text)
                candidates = discover_cast(store, text)
                match = next((item for item in candidates if item['entity_id'] == payload.get('entity_id')), None)
                if match is None:
                    raise WorkspaceConflict('Character candidate is stale or already present; review the list again')
                data = copy.deepcopy(match['candidate'])
                data['attributes'].pop('confidence', None)
                data['attributes'].update(origin='author_added_candidate', provisional=True,
                                          source_evidence=match['evidence'], identity_reviewed=True)
                actor = EntityDef.model_validate(data)
                registry = registry_from_store(store)
                if actor.entity_id in registry:
                    raise WorkspaceConflict('Character ID is already present')
                entity_dir = Path(self.server.entity_dir).resolve()
                target = (entity_dir / (actor.entity_id + '.json')).resolve()
                if target.parent != entity_dir or target.exists():
                    raise WorkspaceConflict('Character file already exists or is outside the workspace')
                registry[actor.entity_id] = actor
                refreshed = build_store(Path(self.server.screenplay_path), Path(self.server.manifest_path),
                    text=text, registry=registry, canon=store.meta['canon'],
                    manifest=manifest_payload(store, store.meta['manifest_payload']),
                    previous_entries=store.meta['id_map'], use_cache=False)
                for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions','manifest_dirty'):
                    if key in store.meta:
                        refreshed.meta[key] = copy.deepcopy(store.meta[key])
                refreshed.meta.setdefault('dirty_entities', []).append(actor.entity_id)
                refreshed.meta.setdefault('dirty_nodes', []).append('ent:' + actor.entity_id)
                refreshed.meta.setdefault('entity_paths', {})[actor.entity_id] = str(target)
                refreshed.meta.setdefault('expected_files', {})[str(target)] = None
                self.server.store, self.server.store_text = refreshed, text
                self._json({'entity_id':actor.entity_id, 'status':'added to unsaved graph; data port is unbound'})
                return

            if route == '/api/state/create':
                if payload.get('reviewed') is not True:
                    raise ValueError('Confirm the new character form before adding it')
                store = self._store_for(text)
                registry = registry_from_store(store)
                entity_id, slug, label = payload.get('entity_id'), payload.get('slug'), payload.get('label')
                actor = registry.get(entity_id)
                if not actor or (actor.canons and store.meta['canon'] not in actor.canons):
                    raise ValueError('Choose a character available in this edition')
                if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', slug):
                    raise ValueError('Form ID must use lowercase letters, digits and underscores, starting with a letter')
                if not isinstance(label, str) or not label.strip() or len(label.strip()) > 160:
                    raise ValueError('Enter a form name of at most 160 characters')
                if any(item.slug == slug for item in actor.states):
                    raise WorkspaceConflict('This character already has that form ID')
                state = StateDef(id=f'{entity_id}.state.{slug}', slug=slug, label=label.strip(),
                    order=max((item.order for item in actor.states), default=-1)+1,
                    canons=[store.meta['canon']], attributes={'provisional':True,
                        'origin':'author_added_option', 'availability':'not established as observed'})
                actor.states.append(state)
                checked = EntityDef.model_validate(actor.model_dump(mode='json'))
                registry[entity_id] = checked
                errors = StoryGraph.from_registry(registry).validate()
                if errors:
                    raise ValueError('; '.join(errors))
                refreshed = build_store(Path(self.server.screenplay_path), Path(self.server.manifest_path),
                    text=text, registry=registry, canon=store.meta['canon'],
                    manifest=manifest_payload(store, store.meta['manifest_payload']),
                    previous_entries=store.meta['id_map'], use_cache=False)
                for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions','manifest_dirty'):
                    if key in store.meta:
                        refreshed.meta[key] = copy.deepcopy(store.meta[key])
                refreshed.meta['dirty_entities'] = sorted(set(refreshed.meta.get('dirty_entities', [])) | {entity_id})
                self.server.store, self.server.store_text = refreshed, text
                self._json({'state_id':state.id, 'port_id':state.data_port.id,
                            'status':'unsaved author-added form; no story event or transition was approved'})
                return

            if route == '/api/transform/create':
                if payload.get('reviewed') is not True:
                    raise ValueError('Confirm the proposed form link before adding it')
                store = self._store_for(text)
                registry = registry_from_store(store)
                entity_id, from_id, to_id = payload.get('entity_id'), payload.get('from_state'), payload.get('to_state')
                actor = registry.get(entity_id)
                if not actor or (actor.canons and store.meta['canon'] not in actor.canons):
                    raise ValueError('Choose a character available in this edition')
                available = {state.id:state for state in actor.states if state.status == 'active' and
                             (not state.canons or store.meta['canon'] in state.canons)}
                if from_id not in available or to_id not in available or from_id == to_id:
                    raise ValueError('Choose two different active forms of the same character')
                from narrative_composer.graph.ids import xform_id
                link_id = xform_id(entity_id, available[from_id].slug, available[to_id].slug)
                if any(item.id == link_id for item in actor.transforms):
                    raise WorkspaceConflict('This form link already exists')
                link = TransformDef(id=link_id, from_state=from_id, to_state=to_id,
                    canons=[store.meta['canon']], attributes={'provisional':True,
                        'origin':'author_added_option', 'review_status':'not established as observed'})
                actor.transforms.append(link)
                registry[entity_id] = EntityDef.model_validate(actor.model_dump(mode='json'))
                errors = StoryGraph.from_registry(registry).validate()
                if errors:
                    raise ValueError('; '.join(errors))
                refreshed = build_store(Path(self.server.screenplay_path), Path(self.server.manifest_path),
                    text=text, registry=registry, canon=store.meta['canon'],
                    manifest=manifest_payload(store, store.meta['manifest_payload']),
                    previous_entries=store.meta['id_map'], use_cache=False)
                for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions','manifest_dirty'):
                    if key in store.meta:
                        refreshed.meta[key] = copy.deepcopy(store.meta[key])
                refreshed.meta['dirty_entities'] = sorted(set(refreshed.meta.get('dirty_entities', [])) | {entity_id})
                self.server.store, self.server.store_text = refreshed, text
                self._json({'transform_id':link.id,
                            'status':'unsaved provisional link; no story event or cause was approved'})
                return

            if route == '/api/proposals':
                store = self._store_for(text)
                from narrative_composer.proposal_store import ProposalStore
                edition = str(Path(self.server.screenplay_path).resolve())
                try:
                    changes = ProposalStore(self.server.screenplay_path).list()
                    history_error = False
                except (OSError, ValueError, sqlite3.Error):
                    changes = []
                    history_error = True
                changes += list(getattr(self.server, 'unstored_proposals', {}).get(edition, {}).values())
                accepted = {decision.get('proposal_id') for decision in store.meta.get('decisions', [])
                            if decision.get('decision') == 'accepted by author'}
                for change in changes:
                    change['history_stale'] = (change.get('base_revision') != store.meta['revision'] or
                                                change.get('rich_revision') != rich_revision or
                                                change.get('edition_path') != str(Path(self.server.screenplay_path).resolve()))
                    if not change['history_stale'] and change.get('eligible', True):
                        violations = current_rewrite_violations(change, store)
                        if violations:
                            change['eligible'] = False
                            change['reason'] = 'Current rewrite checks: ' + '; '.join(violations)
                    if change['proposal_id'] in accepted:
                        change['author_decision'] = 'accepted by author'
                self._json({'patches': changes, 'history_error': history_error})
                return

            if route == '/api/proposal/recover':
                from narrative_composer.proposal_store import ProposalStore
                edition = str(Path(self.server.screenplay_path).resolve())
                pending = getattr(self.server, 'unstored_proposals', {}).get(edition, {})
                proposal = pending.get(payload.get('proposal_id'))
                if not proposal:
                    raise ValueError('No unsaved proposal with that ID in this edition')
                request_id = proposal.get('request_id')
                request_groups = getattr(self.server, 'unstored_requests', {}).get(edition, {})
                group = request_groups.get(request_id) if request_id else None
                if request_id and group is None:
                    raise WorkspaceConflict('The unsaved request cannot be recovered as a complete batch; copy its proposals before closing')
                batch = group['changes'] if group else [proposal]
                durable = [{key:value for key,value in item.items() if key != 'history_unavailable'} for item in batch]
                try:
                    if group:
                        ProposalStore(self.server.screenplay_path).finish_request(request_id, durable, group['planning'])
                    else:
                        ProposalStore(self.server.screenplay_path).append(durable)
                except (OSError, ValueError, sqlite3.Error):
                    raise WorkspaceConflict('Proposal history is still unavailable; copy the candidate before closing')
                for item in batch:
                    pending.pop(item['proposal_id'], None)
                if group:
                    del request_groups[request_id]
                self._json({'saved': True, 'saved_count':len(durable)})
                return

            if route in ('/api/proposal/reject', '/api/proposal/restore'):
                self._store_for(text)
                if payload.get('reviewed') is not True:
                    raise ValueError('An explicit author decision is required')
                from narrative_composer.proposal_store import ProposalStore
                action = 'rejected' if route.endswith('/reject') else 'pending'
                ProposalStore(self.server.screenplay_path).decide(payload.get('proposal_id'), action)
                self._json({'decision': action})
                return

            if route in ('/api/codex/connect', '/api/deepseek/connect', '/api/gemini/connect'):
                session = self._writing_session(route.split('/')[2])
                session.start_connect()
                self._json({'started': True})
                return

            if route in ('/api/deepseek/new', '/api/gemini/new'):
                self._writing_session(route.split('/')[2]).start_new()
                self._json({'started': True, 'previous_session': 'archived locally'})
                return

            if route in ('/api/codex/send', '/api/deepseek/send', '/api/gemini/send'):
                store = self._store_for(text)
                scope = payload.get('context', 'none')
                if scope not in ('none', 'document'):
                    raise ValueError('Unknown context selection')
                context = None
                if scope == 'document':
                    from narrative_composer.graph.data_ports import load_bound_data
                    from narrative_composer.workspace import source_evidence_for_store
                    registry = registry_from_store(store)
                    observations = store.meta['run_graph'].get('state_instances', [])
                    latest = {item['entity']: item['state_id'] for item in observations
                              if item.get('entity') and item.get('state_id')}
                    data_root = Path(self.server.screenplay_path).resolve().parent / 'character_data'
                    bound = {}
                    for key, actor in registry.items():
                        resolution, records = load_bound_data(actor, latest.get(key), data_root)
                        context_records = []
                        for record in records:
                            if record.get('schema_id') == 'narrative.story-index.v1':
                                evidence = source_evidence_for_store(record, store, include_references=True)
                                valid = evidence['status'] == 'current'
                                context_records.append({'dataset_id': record['dataset_id'], 'schema_id': record['schema_id'],
                                    'review_status': 'pending_review', 'source_status': evidence['status'],
                                    'reference_count': evidence['references'],
                                    'references': evidence.get('verified_references', [])[:20] if valid else []})
                            else:
                                context_records.append(record)
                        bound[key] = {'resolution': resolution, 'records': context_records}
                    context = json.dumps({'section': Path(self.server.screenplay_path).name,
                        'revision': store.meta['revision'], 'story_text': text,
                        'manifest': manifest_payload(store, store.meta['manifest_payload']),
                        'characters': {key: actor.model_dump(mode='json') for key, actor in registry.items()},
                        'bound_character_data': bound, 'observed_states': observations,
                        'observation_notice': 'Detected states require author review and do not prove transition causes.'}, ensure_ascii=False)
                    if len(context) > 1500000:
                        raise ValueError('Current document and graph context is too large for this request')
                session = self._writing_session(route.split('/')[2])
                session.start_chat(payload.get('message'), context)
                self._json({'started': True, 'context': scope})
                return

            if route == '/api/beat/create':
                store = self._store_for(text)
                heading, goal = payload.get('slugline'), payload.get('dramatic_goal')
                if not isinstance(heading, str) or not heading.strip() or len(heading) > 240:
                    raise ValueError('Enter a scene heading of at most 240 characters')
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 5000:
                    raise ValueError('Enter a dramatic goal of at most 5000 characters')
                actors = payload.get('active_characters', [])
                registry = registry_from_store(store)
                if not isinstance(actors, list) or any(not isinstance(actor, str) or actor not in registry for actor in actors):
                    raise ValueError('Choose characters from this workspace')
                if len(set(actors)) != len(actors):
                    raise ValueError('A character may be selected only once')
                manifest = manifest_payload(store, store.meta['manifest_payload'])
                beats = manifest.setdefault('beats', {})
                beat_id = payload.get('beat_id') or 'beat_' + uuid.uuid4().hex
                if not isinstance(beat_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', beat_id):
                    raise ValueError('Invalid beat ID')
                if beat_id in beats:
                    raise ValueError('Beat ID already exists')
                current = [StoryBeatNode.model_validate(beat) for beat in beats.values()]
                beat = StoryBeatNode(beat_id=beat_id,
                    chunk_index=max((b.chunk_index for b in current), default=0),
                    beat_order=max((b.beat_order for b in current), default=0) + 1,
                    slugline=heading.strip(), active_characters=actors, dramatic_goal=goal.strip())
                beats[beat_id] = beat.model_dump(mode='json')
                from narrative_composer.models.causal_dag import CausalDAG
                CausalDAG(beats={key: StoryBeatNode.model_validate(value) for key, value in beats.items()}).validate_graph()
                refreshed = build_store(Path(self.server.screenplay_path), Path(self.server.manifest_path),
                    text=text, registry=registry, canon=store.meta['canon'], manifest=manifest,
                    previous_entries=store.meta['id_map'], use_cache=False)
                for key in ('dirty_nodes', 'dirty_entities', 'expected_files', 'entity_paths', 'decisions'):
                    if key in store.meta:
                        refreshed.meta[key] = copy.deepcopy(store.meta[key])
                refreshed.meta['manifest_dirty'] = True
                self.server.store, self.server.store_text = refreshed, text
                self._json({'beat': beat.model_dump(mode='json'), 'status': 'unsaved author plan'})
                return

            if route == '/api/beats':
                from narrative_composer.models.causal_dag import CausalDAG
                store = self._store_for(text)
                manifest = manifest_payload(store, store.meta['manifest_payload'])
                dag = CausalDAG(beats={key: StoryBeatNode.model_validate(value)
                                       for key, value in manifest.get('beats', {}).items()})
                dag.validate_graph()
                registry = registry_from_store(store)
                beats = []
                for beat in dag.get_topological_order():
                    ready = not beat.is_completed and all(dag.beats[p].is_completed for p in beat.prerequisite_beat_ids)
                    names = {name.casefold() for name in beat.active_characters}
                    active_ids = [eid for eid, actor in registry.items() if names &
                                  ({eid.casefold(), actor.display_name.casefold()} | {a.casefold() for a in actor.aliases})]
                    beats.append({'beat_id': beat.beat_id, 'slugline': beat.slugline,
                                  'dramatic_goal': beat.dramatic_goal, 'completed': beat.is_completed,
                                  'actionable': ready, 'active_ids': active_ids})
                self._json({'beats': beats})
                return

            if route == '/api/observation/accept':
                store = self._store_for(text)
                if payload.get('reviewed') is not True:
                    raise ValueError('Review the source observation before accepting it')
                selected = next((o for o in store.meta['run_graph']['observations']
                    if o.get('kind') in ('cue_assertion','state_marker')
                    and o.get('kind') == payload.get('kind') and o.get('entity') == payload.get('entity')
                    and o.get('state') == payload.get('state') and o.get('line') == payload.get('line')
                    and o.get('evidence_hash') == payload.get('evidence_hash')), None)
                if not selected:
                    raise WorkspaceConflict('Source observation changed; refresh before review')
                manifest = manifest_payload(store, store.meta['manifest_payload'])
                review = {'kind':selected['kind'],'entity':selected['entity'],
                    'state_id':selected['entity']+'.state.'+selected['state'], 'line':selected['line'],
                    'evidence_hash':selected['evidence_hash']}
                reviews = manifest.setdefault('reviewed_state_observations', [])
                if review not in reviews:
                    reviews.append(review)
                refreshed = build_store(Path(self.server.screenplay_path),Path(self.server.manifest_path),
                    text=text,registry=registry_from_store(store),canon=store.meta['canon'],manifest=manifest,
                    previous_entries=store.meta['id_map'],use_cache=False)
                for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions'):
                    if key in store.meta:
                        refreshed.meta[key] = copy.deepcopy(store.meta[key])
                refreshed.meta['manifest_dirty'] = True
                self.server.store, self.server.store_text = refreshed, text
                self._json({'observation':review,'status':'state reviewed; transition cause remains pending'})
                return

            if route == '/api/graph':
                import tempfile
                from narrative_composer.graph.viewer import render_viewer
                store = self._store_for(text)
                from narrative_composer.graph.checks import run_checks
                graph = StoryGraph.from_registry(registry_from_store(store))
                from narrative_composer.graph.extract import extract_run
                from narrative_composer.parser.fountain_lexer import FountainParser
                elements = FountainParser.parse(text)
                run = extract_run(elements, graph, store.meta['canon'], 'workspace',
                                  initial_states=store.meta['manifest_payload'].get('initial_character_states'),
                                  reviewed_observations=store.meta['manifest_payload'].get('reviewed_state_observations'))
                violations = run_checks(run, graph, store.meta['canon'], elements)
                displayed = [present_diagnostic(dict(v.model_dump(), source='graph')) for v in violations]
                report = {'summary': {'errors':sum(v['severity']=='ERROR' for v in displayed),
                                      'warnings':sum(v['severity']=='WARNING' for v in displayed)},
                          'violations':displayed, 'suggestions':[], 'discoveries':{}}
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / 'graph.html'
                    render_viewer(store.meta['run_graph'], report, path, graph=graph,
                                  data_root=Path(self.server.screenplay_path).resolve().parent / 'character_data',
                                  initial_entity=payload.get('entity'), initial_mode=payload.get('graph_mode'),
                                  source_store=store)
                    self._json({'html': path.read_text(encoding='utf-8')})
                return

            if route == "/api/node":
                store = self._store_for(text)
                self._json(node_payload(store, payload.get("id", "")))
                return

            if route == '/api/character/trace':
                from narrative_composer.character_trace import character_trace
                store = self._store_for(text)
                node = store.nodes.get(payload.get('id', ''))
                if not node or node.kind != 'entity':
                    raise ValueError('Select a character root')
                self._json(character_trace(store, node.data['entity_id']))
                return

            if route == '/api/state/appearances':
                store = self._store_for(text)
                node = store.nodes.get(payload.get('id', ''))
                if not node or node.kind != 'state':
                    raise ValueError('Select a character form')
                owner = entity_for_node(store, node.id)
                state_id, slug = node.data['id'], node.data['slug']
                found = []
                def add(kind, line, evidence, status):
                    blocks = [n.id for n in store.of_kind('block') if n.data.get('line') == line]
                    found.append({'kind':kind, 'line':line, 'evidence':evidence,
                                  'status':status, 'block_ids':blocks})
                for observation in store.meta['run_graph'].get('observations', []):
                    if observation.get('entity') == owner and observation.get('state') == slug:
                        add(observation.get('kind'), observation.get('line'), observation.get('evidence', ''),
                            'reviewed observation' if observation.get('reviewed') else
                            'accepted transition' if observation.get('accepted') else 'unreviewed observation')
                for instance in store.meta['run_graph'].get('state_instances', []):
                    if instance.get('entity') == owner and instance.get('state_id') == state_id:
                        add('state_instance', instance.get('at', {}).get('line'), instance.get('evidence', ''),
                            'graph state: ' + str(instance.get('source', 'unknown')))
                self._json({'entity':owner, 'state_id':state_id, 'appearances':found,
                            'notice':'Observations and graph states require source review; an appearance does not approve a transition cause.'})
                return

            if route == '/api/data/inspect':
                from narrative_composer.graph.data_ports import load_bound_data
                from narrative_composer.workspace import source_evidence_for_store
                store = self._store_for(text)
                port_id = payload.get('id', '')
                node = store.nodes.get(port_id)
                if not node or node.kind != 'data_port':
                    raise ValueError('Select a character or form data port')
                owner = store.incoming(port_id, 'has_data_port')
                if len(owner) != 1:
                    raise ValueError('Data port has no unique owner')
                entity_id = entity_for_node(store, port_id)
                actor = registry_from_store(store)[entity_id]
                owner_node = store.node(owner[0].src)
                state_id = owner_node.data['id'] if owner_node.kind == 'state' else None
                info, records = load_bound_data(actor, state_id,
                    Path(self.server.screenplay_path).resolve().parent / 'character_data')
                source_name = Path(self.server.screenplay_path).name
                source_digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                evidence = next((source_evidence_for_store(record, store, include_references=True) for record in records
                                 if record.get('schema_id') == 'narrative.story-index.v1'),
                                {'status':'not indexed', 'references':0})
                self._json({'entity': entity_id, 'state_id': state_id,
                            'data_input': info, 'records': records,
                            'source_evidence': evidence,
                            'current_source': {'file': source_name, 'sha256': source_digest}})
                return

            if route == "/api/node/update":
                store = self._store_for(text)
                updated_text = apply_node_edit(store, payload.get("id", ""), payload.get("value", ""))
                self.server.store_text = None
                store = self._store_for(updated_text if updated_text is not None else text)
                self._json(
                    {
                        "text": updated_text,
                        "node": node_payload(store, payload.get("id", "")),
                        "summary": summary(store),
                    }
                )
                return

            if route == "/api/recook":
                provider = payload.get("provider") or getattr(self.server, 'default_provider', 'deepseek')
                if provider not in ("mock", "codex", "api", "session", "venice", "gemini", "gemini_session", "deepseek"):
                    self._json({"error": f"unknown provider: {provider}"}, 400)
                    return
                store = NodeStore.from_dict(self._store_for(text).to_dict())
                source_path = Path(self.server.screenplay_path).resolve()
                manifest_path = Path(self.server.manifest_path).resolve()
                selected_provider = self._provider(provider)
                stats = {}
                limit = 1 if provider == 'codex' else 2 if provider in ('api', 'session', 'venice', 'gemini', 'gemini_session', 'deepseek') else None
                with guard_identical_provider_request(self.server, route, source_path, payload), provider_work_without_commit_lock():
                    patches = plan_patches(text, manifest_path, provider_type=provider,
                        manifest=store.meta['manifest_payload'], document=document_from_store(store),
                        neural_limit=limit, stats=stats, provider=selected_provider)
                changes = [dict(patch.to_dict(), provider='deterministic' if patch.tier == 'tier_1_surgical' else provider,
                    model_name='gpt-6.1-terra' if provider == 'codex' and patch.tier != 'tier_1_surgical' else '',
                    reasoning_effort='max' if provider == 'codex' and patch.tier != 'tier_1_surgical' else '') for patch in patches]
                self._json({'patches': self._remember_changes(store, changes, rich_revision, source_path, request_id, stats), 'planning': stats})
                return

            if route == '/api/condition':
                from narrative_composer.condition import plan_conditioning
                from narrative_composer.prose.providers import create_prose_provider
                store = NodeStore.from_dict(self._store_for(text).to_dict())
                source_path = Path(self.server.screenplay_path).resolve()
                provider_type = payload.get('provider') or getattr(self.server, 'default_provider', 'deepseek')
                if provider_type not in ('mock', 'codex', 'venice', 'api', 'gemini', 'gemini_session', 'deepseek'):
                    raise ValueError('Unknown provider')
                limit = payload.get('limit', 1 if provider_type == 'codex' else 2)
                if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
                    raise ValueError('Conditioning limit must be an integer from 1 to 10')
                selected_provider = self._provider(provider_type)
                with guard_identical_provider_request(self.server, route, source_path, payload), provider_work_without_commit_lock():
                    proposals = plan_conditioning(text, selected_provider, limit=limit,
                        manifest=store.meta['manifest_payload'], document=document_from_store(store),
                        target_block_ids=payload.get('target_block_ids'))
                changes = [dict(p.to_dict(), rule_id='PROSE_CONDITIONING',
                           rationale=p.reason, eligible=p.accepted) for p in proposals]
                self._json({'patches': self._remember_changes(store, changes, rich_revision, source_path, request_id)})
                return

            if route == '/api/condition/target':
                store = self._store_for(text)
                line = payload.get('line')
                if type(line) is not int or line < 1:
                    raise ValueError('Choose one story paragraph')
                matches = [node for node in store.of_kind('block')
                           if node.data.get('line') == line and node.data.get('role') == 'action']
                if len(matches) != 1:
                    raise ValueError('Select a single action paragraph; dialogue, notes and headings are not supported')
                self._json({'block_id':matches[0].id.removeprefix('blk:'), 'line':line})
                return

            if route == '/api/compose':
                from narrative_composer.workspace import compose_beat
                from narrative_composer.prose.providers import create_prose_provider
                store = NodeStore.from_dict(self._store_for(text).to_dict())
                source_path = Path(self.server.screenplay_path).resolve()
                provider_type = payload.get('provider') or getattr(self.server, 'default_provider', 'deepseek')
                if provider_type not in ('mock', 'codex', 'venice', 'api', 'gemini', 'gemini_session', 'deepseek'):
                    raise ValueError('Unknown provider')
                provider = self._provider(provider_type)
                with guard_identical_provider_request(self.server, route, source_path, payload), provider_work_without_commit_lock():
                    candidate = compose_beat(store, provider, beat_id=payload.get('beat_id') or None,
                                             state_overrides=payload.get('state_overrides'))
                candidate.update(provider=getattr(provider, 'provider_id', provider_type),
                                 model_name=getattr(provider, 'model_name', ''),
                                 reasoning_effort=getattr(provider, 'reasoning_effort', ''))
                self._json({'patches': self._remember_changes(store, [candidate], rich_revision, source_path, request_id)})
                return

            if route == '/api/proposal/apply':
                store = self._store_for(text)
                from narrative_composer.proposal_store import ProposalStore
                change = ProposalStore(self.server.screenplay_path).get(payload.get('proposal_id'))
                if not change:
                    change = getattr(self.server, 'pending_changes', {}).get(payload.get('proposal_id'))
                if not change or change['base_revision'] != store.meta['revision']:
                    raise WorkspaceConflict('Proposal is stale; plan again against the current revision')
                if change.get('history_unavailable'):
                    raise WorkspaceConflict('Save this proposal to history before applying it')
                if change.get('edition_path') != str(Path(self.server.screenplay_path).resolve()):
                    raise WorkspaceConflict('Proposal belongs to a different or unidentified edition; plan again here')
                if change.get('author_decision') == 'rejected':
                    raise ValueError('This proposal was rejected; restore it for review first')
                if change.get('rich_revision') != rich_revision:
                    raise WorkspaceConflict('Document formatting changed; plan this proposal again')
                if payload.get('reviewed') is not True or not change.get('eligible', True):
                    raise ValueError('An eligible proposal requires explicit author review')
                if change.get('kind') == 'beat':
                    from narrative_composer.workspace import compose_beat
                    if not isinstance(change.get('data_dependencies'), dict):
                        raise WorkspaceConflict('This older proposal has no character-data snapshot; plan again')
                    addition, manifest = compose_beat(store, reviewed_text=change['proposed'],
                        beat_id=change['beat_id'], state_overrides=change.get('state_overrides'),
                        expected_data_dependencies=change['data_dependencies'])
                    newline = '\r\n' if text.endswith('\r\n') else '\r' if text.endswith('\r') else '\n'
                    normalized_tail = text.replace('\r\n', '\n').replace('\r', '\n')
                    separator = '' if normalized_tail.endswith('\n\n') else newline if normalized_tail.endswith('\n') else newline * 2
                    updated = text + separator + addition + ('' if addition.endswith(('\n', '\r')) else newline)
                    refreshed = build_store(Path(self.server.screenplay_path),Path(self.server.manifest_path),
                        text=updated,registry=registry_from_store(store),canon=store.meta['canon'],
                        manifest=manifest,previous_entries=store.meta['id_map'],use_cache=False)
                    for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions'):
                        if key in store.meta:
                            refreshed.meta[key] = copy.deepcopy(store.meta[key])
                    refreshed.meta['manifest_dirty'] = True
                else:
                    node = store.node('blk:' + change['block_id'])
                    if node.data['text'] != change['original']:
                        raise WorkspaceConflict('Original block changed')
                    violations = current_rewrite_violations(change, store)
                    if violations:
                        raise ValueError('Proposal no longer passes rewrite checks: ' + '; '.join(violations))
                    candidate = NodeStore.from_dict(store.to_dict())
                    updated = apply_node_edit(candidate, node.id, change['proposed'])
                    refreshed = build_store(Path(self.server.screenplay_path),Path(self.server.manifest_path),
                        text=updated,registry=registry_from_store(candidate),canon=store.meta['canon'],
                        manifest=manifest_payload(candidate,candidate.meta['manifest_payload']),
                        previous_entries=candidate.meta['id_map'],use_cache=False)
                    added = introduced_errors(store,refreshed)
                    if added:
                        raise ValueError('Proposal introduces blocking checks or unreviewed state observations: ' +
                                         '; '.join(d['rule_id'] for d in added[:5]))
                    for key in ('dirty_nodes','dirty_entities','expected_files','entity_paths','decisions','manifest_dirty'):
                        if key in candidate.meta:
                            refreshed.meta[key] = copy.deepcopy(candidate.meta[key])
                if payload.get('preview_only') is True:
                    self._json({'text': updated, 'kind': change.get('kind'), 'preview_only': True})
                    return
                self.server.store, self.server.store_text = refreshed, updated
                refreshed.meta.setdefault('decisions', []).append({
                    'proposal_id': change['proposal_id'], 'base_revision': change['base_revision'],
                    'resulting_revision': refreshed.meta['revision'], 'decision': 'accepted by author',
                    'original': change['original'], 'proposed': change['proposed']})
                self._json({'text': updated, 'decision': 'accepted by author',
                    'diagnostics': refreshed.meta['diagnostics']})
                return

            if route == '/api/export':
                store = self._store_for(text)
                fmt = payload.get('format', 'source')
                if fmt == 'source':
                    content, ext, mime = to_text(store), '.md', 'text/markdown'
                elif fmt == 'reader':
                    theme = replace(GENERIC_THEME, page_title=Path(self.server.screenplay_path).stem,
                        verified_note='Authored draft', hero_h1_html='Story', graph_href='', compact=True)
                    content, ext, mime = render_reader(document_from_store(store), theme), '.html', 'text/html'
                elif fmt == 'project':
                    content, ext, mime = json.dumps(project_report(store), indent=2, ensure_ascii=False), '.json', 'application/json'
                else:
                    raise ValueError('Unknown export format')
                self._json({'content': content, 'filename': Path(self.server.screenplay_path).stem + ext, 'mime': mime})
                return

            if route == "/api/save":
                store = self._store_for(text)
                saved = save_workspace(
                    store,
                    text,
                    Path(self.server.screenplay_path),
                    entity_dir=Path(self.server.entity_dir),
                    manifest_path=Path(self.server.manifest_path),
                    nodes_out=snapshot_path(Path(self.server.screenplay_path)),
                    rich_document=rich_document,
                )
                if rich_revision is not None:
                    self.server.rich_baseline = rich_revision
                self._json({"ok": True, "saved": saved})
                return

        except WorkspaceConflict as exc:
            self._json({'error': str(exc)}, 409)
            return
        except KeyError as exc:
            self._json({"error": f"unknown node: {exc}"}, 404)
            return
        except (ValueError, FileNotFoundError) as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # provider configuration errors and the like
            self._json({"error": f"request failed: {exc}"}, 400)
            return

        self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _remember_changes(self, store, changes, rich_revision=None, source_path=None, request_id=None, planning=None):
        import uuid
        from narrative_composer.proposal_store import ProposalStore
        source_path = Path(source_path or self.server.screenplay_path).resolve()
        trace_by_block = {}
        if any(change.get('block_id') for change in changes):
            from narrative_composer.character_trace import character_trace
            for entity in store.of_kind('entity'):
                entity_id = entity.data['entity_id']
                for item in character_trace(store, entity_id)['entries']:
                    trace_by_block.setdefault(item['block_id'], []).append({
                        'entity':entity_id, 'kind':item['kind'], 'state_id':item.get('state_id'),
                        'status':item['status']})
        for change in changes:
            change.update(proposal_id=uuid.uuid4().hex, base_revision=store.meta['revision'],
                          rich_revision=rich_revision, edition_path=str(source_path))
            block_id = change.get('block_id') or ''
            block_id = block_id if block_id.startswith('blk:') else 'blk:' + block_id if block_id else None
            target = store.nodes.get(block_id) if block_id else None
            line = target.data.get('line') if target else None
            observations = [dict(kind=item.get('kind'), entity=item.get('entity'), state=item.get('state'),
                                 line=item.get('line'), reviewed=item.get('reviewed', False),
                                 accepted=item.get('accepted', False))
                            for item in store.meta.get('run_graph', {}).get('observations', [])
                            if line is not None and item.get('line') == line]
            findings = [present_diagnostic(item) for item in store.meta.get('diagnostics', [])
                        if block_id and item.get('node_id') == block_id and item.get('source') == 'graph']
            change['graph_context'] = {'edition':source_path.name,
                'source_sha256':hashlib.sha256(to_text(store).encode('utf-8')).hexdigest(),
                'target_block_id':block_id, 'line':line, 'observations':observations,
                'findings':findings, 'state_assumptions':change.get('state_assumptions', []),
                'character_links':trace_by_block.get(block_id, []),
                'authored_evidence':change.get('authored_evidence', []),
                'notice':'Source observations are review material, not approved transition causes; newly introduced unresolved states remain blocked.'}
            if request_id:
                change['request_id'] = request_id
        same_section = source_path == Path(self.server.screenplay_path).resolve()
        current = getattr(self.server, 'store', None)
        stale = not same_section or current is None or current.meta['revision'] != store.meta['revision']
        for change in changes:
            change['history_stale'] = stale
        try:
            if request_id:
                ProposalStore(source_path).finish_request(request_id, changes, planning)
            else:
                ProposalStore(source_path).append(changes)
        except (OSError, ValueError, sqlite3.Error):
            if not changes:
                raise WorkspaceConflict('Request completed with no proposals, but its outcome could not be saved. Check history before starting another request.')
            if not hasattr(self.server, 'unstored_proposals'):
                self.server.unstored_proposals = {}
            pending = self.server.unstored_proposals.setdefault(str(source_path), {})
            for change in changes:
                change['history_unavailable'] = True
                pending[change['proposal_id']] = change
            if request_id:
                if not hasattr(self.server, 'unstored_requests'):
                    self.server.unstored_requests = {}
                groups = self.server.unstored_requests.setdefault(str(source_path), {})
                groups[request_id] = {'changes':changes, 'planning':planning}
        if same_section:
            if not hasattr(self.server, 'pending_changes'):
                self.server.pending_changes = {}
            self.server.pending_changes.update({change['proposal_id']: change for change in changes})
        return [dict(change, history_stale=stale) for change in changes]


def serve(
    screenplay_path: Path = DEFAULT_SCREENPLAY,
    host: str = "127.0.0.1",
    port: int = 8765,
    manifest_path: Path = DEFAULT_MANIFEST,
    entity_dir: Path = DEFAULT_ENTITY_DIR,
    canon: str = 'hot_scoomp_main',
    default_provider: str = 'deepseek',
) -> None:
    screenplay_path = Path(screenplay_path).resolve()
    recover_transactions(screenplay_path.with_suffix(screenplay_path.suffix + '.revisions'), [Path(entity_dir)])
    httpd = ThreadingHTTPServer((host, port), EditorHandler)
    httpd.screenplay_path = screenplay_path  # type: ignore[attr-defined]
    httpd.manifest_path = Path(manifest_path).resolve()  # type: ignore[attr-defined]
    httpd.entity_dir = Path(entity_dir).resolve()  # type: ignore[attr-defined]
    candidate_timeline = screenplay_path.parent / 'timeline.json'
    httpd.timeline_path = candidate_timeline if candidate_timeline.is_file() else None
    httpd.canon = canon
    httpd.default_provider = default_provider
    httpd.reaction_cache = {}
    httpd.store = None  # type: ignore[attr-defined]
    httpd.store_text = None  # type: ignore[attr-defined]
    print(f"Narrative Composer node editor: http://{host}:{port}")
    print(f"Editing: {screenplay_path}")
    print("Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if hasattr(httpd, 'codex_session'):
            httpd.codex_session.close()
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Node-backed live-preview editor")
    parser.add_argument("--file", default=str(DEFAULT_SCREENPLAY), help="Screenplay to edit")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (loopback only by default)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Manifest for diagnostics")
    parser.add_argument("--entity-dir", default=str(DEFAULT_ENTITY_DIR), help="Where character JSON is written")
    parser.add_argument('--canon', default='hot_scoomp_main')
    parser.add_argument('--provider', choices=('codex', 'mock', 'venice', 'api', 'deepseek', 'gemini_session'), default='deepseek',
                        help='Provider selected when the editor opens (default: deepseek)')
    args = parser.parse_args()
    serve(
        Path(args.file),
        host=args.host,
        port=args.port,
        manifest_path=Path(args.manifest),
        entity_dir=Path(args.entity_dir),
        canon=args.canon,
        default_provider=args.provider,
    )


if __name__ == "__main__":
    main()
