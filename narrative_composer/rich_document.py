"""A loss-aware Tiptap document paired with an exact screenplay source projection.

The source remains the graph's text input; rich formatting and stable line IDs live
in a versioned sidecar committed with the source. An out-of-band source edit makes
the sidecar stale and must be resolved rather than silently discarded.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from bisect import bisect_right
from pathlib import Path

from narrative_composer.persistence import WorkspaceConflict


SCHEMA_VERSION = 1
LAYOUTS = {'body', 'title', 'scene', 'cue', 'dialogue', 'note'}
ALIGNMENTS = {'left', 'center', 'right'}
MARKS = {'bold', 'italic', 'underline', 'strike'}


def sidecar_path(story_path: Path) -> Path:
    path = Path(story_path)
    return path.with_suffix(path.suffix + '.rich.json')


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalized(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n')


def new_document(text: str) -> dict:
    lines = []
    for line in normalized(text).split('\n'):
        paragraph = {'type': 'paragraph', 'attrs': {'id': str(uuid.uuid4()),
                     'layout': 'body', 'align': 'left'}}
        if line:
            paragraph['content'] = [{'type': 'text', 'text': line}]
        lines.append(paragraph)
    return {'type': 'doc', 'content': lines}


def import_word_formatting(path: Path, text: str) -> dict | None:
    """Import direct run marks only when every recorded source span still matches."""
    extraction_path = Path(path).with_suffix('.extraction.json')
    if not extraction_path.is_file():
        return None
    try:
        data = json.loads(extraction_path.read_text(encoding='utf-8'))
        paragraphs = data['paragraphs']
        if not isinstance(paragraphs, list) or not paragraphs or normalized(text) != text:
            return None
        starts = [0] + [i + 1 for i, char in enumerate(text) if char == '\n']
        lines = text.split('\n')
        styles = [[] for _ in lines]
        last_end = 0
        for paragraph in paragraphs:
            start, end = paragraph['projection_char_start'], paragraph['projection_char_end']
            value, runs = paragraph['text'], paragraph['runs']
            if (not isinstance(start, int) or not isinstance(end, int) or start < last_end or end < start
                    or text[start:end] != value or ''.join(run['text'] for run in runs) != value):
                return None
            last_end = end
            cursor = start
            for run in runs:
                marks = [name for name in ('bold', 'italic', 'underline') if run.get(name) is True]
                for fragment in run['text'].splitlines(keepends=True):
                    body = fragment[:-1] if fragment.endswith('\n') else fragment
                    if marks and body:
                        line = bisect_right(starts, cursor) - 1
                        column = cursor - starts[line]
                        styles[line].append((column, column + len(body), marks))
                    cursor += len(fragment)
        doc = new_document(text)
        for paragraph, value, ranges in zip(doc['content'], lines, styles):
            if not ranges:
                continue
            fragments, cursor = [], 0
            for start, end, marks in ranges:
                if start < cursor or end > len(value):
                    return None
                if start > cursor:
                    fragments.append({'type': 'text', 'text': value[cursor:start]})
                fragments.append({'type': 'text', 'text': value[start:end],
                                  'marks': [{'type': mark} for mark in marks]})
                cursor = end
            if cursor < len(value):
                fragments.append({'type': 'text', 'text': value[cursor:]})
            paragraph['content'] = fragments
        validate_document(doc, text)
        return doc
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def validate_document(document: dict, text: str) -> str:
    """Reject unsupported data rather than letting the editor normalize it away."""
    if not isinstance(document, dict) or set(document) != {'type', 'content'} or document['type'] != 'doc':
        raise ValueError('Unsupported rich document schema')
    paragraphs = document['content']
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError('Rich document needs at least one paragraph')
    seen, lines = set(), []
    for paragraph in paragraphs:
        if (not isinstance(paragraph, dict) or set(paragraph) - {'type', 'attrs', 'content'}
                or paragraph.get('type') != 'paragraph'):
            raise ValueError('Unsupported rich document block')
        attrs = paragraph.get('attrs')
        if not isinstance(attrs, dict) or set(attrs) != {'id', 'layout', 'align'}:
            raise ValueError('Unsupported paragraph attributes')
        identity = attrs['id']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity) or identity in seen:
            raise ValueError('Missing or duplicate rich paragraph ID')
        seen.add(identity)
        if attrs['layout'] not in LAYOUTS or attrs['align'] not in ALIGNMENTS:
            raise ValueError('Unsupported paragraph layout')
        content = paragraph.get('content', [])
        if not isinstance(content, list):
            raise ValueError('Unsupported paragraph content')
        fragments = []
        for node in content:
            if (not isinstance(node, dict) or set(node) - {'type', 'text', 'marks'}
                    or node.get('type') != 'text' or not isinstance(node.get('text'), str)
                    or not node['text'] or '\n' in node['text'] or '\r' in node['text']):
                raise ValueError('Unsupported rich text content')
            marks = node.get('marks', [])
            if not isinstance(marks, list) or any(not isinstance(mark, dict) or set(mark) != {'type'}
                                                  or mark['type'] not in MARKS for mark in marks):
                raise ValueError('Unsupported rich text formatting')
            if len({mark['type'] for mark in marks}) != len(marks):
                raise ValueError('Duplicate rich text formatting')
            fragments.append(node['text'])
        lines.append(''.join(fragments))
    if '\n'.join(lines) != normalized(text):
        raise WorkspaceConflict('Rich document and story text do not match; refresh before saving')
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def load_document(path: Path, text: str) -> tuple[dict, str]:
    sidecar = sidecar_path(path)
    if not sidecar.exists():
        imported = import_word_formatting(path, text)
        if imported is not None:
            return imported, 'word_import'
        return new_document(text), 'new'
    try:
        saved = json.loads(sidecar.read_text(encoding='utf-8'))
        if not isinstance(saved, dict) or set(saved) != {'schema_version', 'source_sha256', 'document'}:
            raise ValueError('Unsupported document sidecar')
        if saved['schema_version'] != SCHEMA_VERSION:
            raise ValueError('Unsupported document sidecar version')
        if saved['source_sha256'] != source_hash(text):
            raise WorkspaceConflict('Story text changed outside the rich editor; its formatting needs recovery')
        validate_document(saved['document'], text)
        return saved['document'], 'saved'
    except WorkspaceConflict:
        raise
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise WorkspaceConflict('Rich document sidecar cannot be safely loaded: ' + str(exc)) from exc


def sidecar_content(document: dict, text: str) -> str:
    validate_document(document, text)
    return json.dumps({'schema_version': SCHEMA_VERSION, 'source_sha256': source_hash(text),
                       'document': document}, ensure_ascii=False, indent=2) + '\n'
