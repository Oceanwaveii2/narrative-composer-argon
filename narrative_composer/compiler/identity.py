"""
Stable block identity across edits.

Content-addressed IDs change when a block's own text changes, and duplicate lines are
disambiguated only by order. This module keeps a persisted sidecar map of known blocks and
reconciles a freshly parsed document against it:

  1. exact (role, text) matches keep their ID, choosing the nearest line when the same
     text appears more than once;
  2. remaining blocks are matched to leftover entries of the same role by line proximity,
     so an edited block keeps its identity;
  3. anything left over gets a fresh ID.

The sidecar is written on save, next to the screenplay (`<screenplay>.ids.json`).
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from narrative_composer.compiler.document import Document, rebuild_scenes
from narrative_composer.persistence import WorkspaceConflict

# How far a block may move and still be considered "the same block, edited".
MATCH_WINDOW = 8


class IdentitySidecarError(WorkspaceConflict):
    """An existing identity map cannot be safely interpreted."""


def sidecar_path(script_path: Path) -> Path:
    script_path = Path(script_path)
    return script_path.with_suffix(script_path.suffix + ".ids.json")


def entries_from_document(document: Document) -> List[Dict[str, Any]]:
    return [
        {
            "id": block.id,
            "role": block.role.value,
            "text": block.text,
            "line": block.line,
        }
        for block in document.blocks
    ]


def load_entries(path: Path) -> Optional[List[Dict[str, Any]]]:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IdentitySidecarError(f'Identity sidecar {path.name} is unreadable or invalid. Preserve the story and sidecar; follow IDENTITY_RECOVERY.md before restoring a matched backup.') from exc
    if not isinstance(data, list) or any(
        not isinstance(entry, dict) or any(not isinstance(entry.get(key), str) for key in ('id', 'role', 'text'))
        or not entry['id'] or not entry['role']
        or ('line' in entry and (type(entry['line']) is not int or entry['line'] < 0)) for entry in data
    ):
        raise IdentitySidecarError(f'Identity sidecar {path.name} contains malformed entries. Preserve the story and sidecar; follow IDENTITY_RECOVERY.md before restoring a matched backup.')
    return data


def save_entries(path: Path, entries: List[Dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return path


def new_block_id(role: str) -> str:
    return f"{role}-{secrets.token_hex(4)}"


def stabilize(document: Document, previous: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Reconciles block IDs against the previous identity map and returns the new map."""
    if not previous:
        return entries_from_document(document)

    buckets: Dict[tuple, List[Dict[str, Any]]] = {}
    for entry in previous:
        buckets.setdefault((entry.get("role"), entry.get("text")), []).append(entry)

    claimed: set[int] = set()
    used_ids: set[str] = set()
    unmatched = []

    def fresh(role: str) -> str:
        candidate = new_block_id(role)
        while candidate in used_ids:
            candidate = new_block_id(role)
        used_ids.add(candidate)
        return candidate

    for block in document.blocks:
        bucket = buckets.get((block.role.value, block.text))
        if bucket:
            best = min(bucket, key=lambda entry: abs(int(entry.get("line", 0)) - block.line))
            bucket.remove(best)
            claimed.add(id(best))
            # A sidecar written before ID uniqueness was enforced can contain duplicate
            # IDs; never let two blocks share one identity.
            if best["id"] in used_ids:
                block.id = fresh(block.role.value)
            else:
                block.id = best["id"]
                used_ids.add(block.id)
        else:
            unmatched.append(block)

    leftovers = [entry for entry in previous if id(entry) not in claimed]

    for block in unmatched:
        candidates = [
            entry
            for entry in leftovers
            if entry.get("role") == block.role.value and entry.get("id") not in used_ids
        ]
        if candidates:
            best = min(candidates, key=lambda entry: abs(int(entry.get("line", 0)) - block.line))
            if abs(int(best.get("line", 0)) - block.line) <= MATCH_WINDOW:
                block.id = best["id"]
                used_ids.add(block.id)
                leftovers.remove(best)
                continue
        block.id = fresh(block.role.value)

    rebuild_scenes(document)
    return entries_from_document(document)
