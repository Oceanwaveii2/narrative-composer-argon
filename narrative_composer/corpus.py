"""Prepare a provenance-preserving, multi-edition story exercise workspace.

Outline extraction is a review copy, not a lossless conversion of Word or PDF.
Original source bytes are retained and no alternative edition is made canon.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

from narrative_composer.graph.registry import DEFAULT_CHARACTERS_DIR
from narrative_composer.persistence import commit_files, recover_transactions
from narrative_composer.story import EMPTY_MANIFEST


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word_story_projection(raw: bytes) -> tuple[str, dict]:
    """Project Word paragraphs to plain text while recording source locations.

    This is intentionally not a Word round trip: formatting and other source
    features remain in the original and in the extracted run metadata.
    """
    from docx import Document

    doc = Document(io.BytesIO(raw))
    pieces, paragraphs = [], []
    offset = 0
    line = 1
    for number, paragraph in enumerate(doc.paragraphs, 1):
        text = paragraph.text
        start = offset
        end = start + len(text)
        paragraphs.append({
            'paragraph': number,
            'text': text,
            'projection_char_start': start,
            'projection_char_end': end,
            'projection_start_line': line,
            'projection_end_line': line + text.count('\n'),
            'style': paragraph.style.name if paragraph.style else None,
            'runs': [{'text': run.text, 'bold': run.bold, 'italic': run.italic,
                      'underline': run.underline if isinstance(run.underline, bool) else None}
                     for run in paragraph.runs],
        })
        pieces.append(text + '\n\n')
        offset = end + 2
        line += text.count('\n') + 2
    projection = ''.join(pieces)
    return projection, {
        'paragraphs': paragraphs,
        'projection_offsets': 'Unicode code points; end is exclusive',
        'warnings': [
            'Plain-text review projection; Word formatting is recorded separately and not rendered here.',
            'Original Word file remains the source; this projection is not a lossless Word conversion.',
            f'{len(doc.tables)} tables and {len(doc.inline_shapes)} inline images were not projected into active text.',
            'Review the extracted story and its edition-specific chronology before treating it as accepted canon.',
        ],
    }


def add_word_variant(workspace: Path, source: Path, variant_id: str) -> dict:
    """Add one separate Word edition without replacing existing workspace files."""
    if not re.fullmatch(r'[a-z][a-z0-9_]*', variant_id):
        raise ValueError('Variant ID must use lowercase letters, numbers and underscores')
    root = Path(workspace).resolve()
    source = Path(source).resolve()
    index_path = root / 'timeline.json'
    journal_root = root / 'timeline.revisions'
    recover_transactions(journal_root)
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes.decode('utf-8'))
    source_key = variant_id + '_docx'
    if source_key in index.get('sources', {}) or any(s.get('id') == variant_id for s in index.get('sections', [])):
        raise FileExistsError('This variant ID already exists; select a new ID')
    raw = source.read_bytes()
    projection, extracted = word_story_projection(raw)
    source_copy = root / 'sources' / (source_key + '.docx')
    story = root / (variant_id + '.md')
    extraction = root / (variant_id + '.extraction.json')
    manifest = root / (variant_id + '.manifest.json')
    targets = [source_copy, story, extraction, manifest]
    if any(not path.resolve().is_relative_to(root) for path in targets):
        raise ValueError('Variant files must remain inside the timeline workspace')
    if any(path.exists() or path.is_symlink() for path in targets):
        raise FileExistsError('A variant file already exists; no files were replaced')
    index.setdefault('sources', {})[source_key] = {
        'original': str(source), 'copy': source_copy.relative_to(root).as_posix(), 'sha256': sha256(raw),
    }
    section = {
        'id': variant_id, 'story': story.name, 'manifest': manifest.name,
        'canon': 'hot_scoomp_main', 'source': source_key,
        'sha256': sha256(projection.encode('utf-8')),
        'status': 'separate story variant; plain-text extraction and formatting require review',
    }
    index.setdefault('sections', []).append(section)
    updates = {
        source_copy: raw,
        story: projection.encode('utf-8'),
        extraction: (json.dumps(extracted, ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
        manifest: (json.dumps(copy.deepcopy(EMPTY_MANIFEST), ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
        index_path: (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
    }
    expected = {str(path.resolve()): None for path in targets}
    expected[str(index_path.resolve())] = sha256(index_bytes)
    commit_files(updates, expected, journal_root)
    return section


def word_outline(path: Path, excluded_beats: set[str] | None = None) -> dict:
    from docx import Document
    doc = Document(str(path))
    excluded_beats = excluded_beats or set()
    current_beat = None
    paragraphs = []
    for number, paragraph in enumerate(doc.paragraphs, 1):
        text = paragraph.text
        stripped = text.strip()
        match = re.match(r'^Beat\s+([0-9]+[A-Z]?)\s*:', stripped, re.I)
        if match:
            current_beat = match.group(1).upper()
        elif re.match(r'^Act\s+\d+\s*:', stripped, re.I):
            current_beat = None
        if not stripped:
            role = 'blank'
        elif stripped.startswith('http'):
            role = 'reference'
        elif stripped.startswith('Below is') or stripped.startswith('End of Main Story Outline') or stripped == '⁂':
            role = 'document_metadata'
        elif stripped.startswith('Episode Outline:'):
            role = 'title'
        elif re.match(r'^Act\s+\d+\s*:', stripped, re.I):
            role = 'act'
        elif match:
            role = 'beat'
        elif stripped.startswith('Notes:'):
            role = 'outline_note'
        elif stripped.startswith('Dialogue samples:'):
            role = 'sample_dialogue'
        else:
            role = 'outline_text'
        paragraphs.append({'paragraph':number, 'beat':current_beat, 'role':role, 'text':text,
            'included':current_beat not in excluded_beats and role not in ('reference','document_metadata'),
            'runs':[{'text':run.text,'bold':run.bold,'italic':run.italic} for run in paragraph.runs]})
    return {'paragraphs':paragraphs, 'warnings':[
        'Word extraction is a review projection; source file, images, and unsupported formatting remain authoritative.',
        f'{len(doc.tables)} tables and {len(doc.inline_shapes)} inline images were not projected into active text.'
    ]}


def outline_markdown(extracted: dict) -> str:
    lines = []
    for paragraph in extracted['paragraphs']:
        if not paragraph['included']:
            continue
        text, role = paragraph['text'], paragraph['role']
        if role == 'blank':
            lines.append('')
        elif role in ('title', 'act', 'beat'):
            lines.append(('#' if role in ('title','act') else '##') + ' ' + text.strip())
        else:
            # Outline prose and sample dialogue are notes, not accepted screenplay.
            lines.extend('> ' + line for line in text.split('\n'))
    return '\n'.join(lines).rstrip() + '\n'


def pdf_outline(path: Path) -> dict:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode='layout') or ''
        pages.append({'page':number, 'text':text, 'unmapped_characters':text.count('\x00')})
    return {'pages':pages, 'warnings':[
        'PDF extraction may reorder content, omit formatting or contain unmapped characters; compare with original pages.'
    ]}


def pdf_outline_markdown(extracted: dict) -> str:
    lines = ['# B Story — extracted outline for review']
    for page in extracted['pages']:
        lines.append(f"## Source page {page['page']}")
        for line in page['text'].splitlines():
            text = line.strip().replace('\x00', '�')
            if not text:
                lines.append('')
            elif text.startswith(('http://','https://')) or text.lower().startswith('now do story b on it own'):
                continue
            else:
                lines.append('> ' + text)
    return '\n'.join(lines).rstrip() + '\n'


def prepare_timeline(chronology: Path, main_docx: Path, main_pdf: Path, b_pdf: Path, destination: Path) -> dict:
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('Choose a new destination; existing authored work is never overwritten')
    files = {'chronology':Path(chronology), 'main_docx':Path(main_docx),
             'main_pdf':Path(main_pdf), 'b_pdf':Path(b_pdf)}
    raw = {key:path.read_bytes() for key,path in files.items()}
    lines = raw['chronology'].decode('utf-8').splitlines(keepends=True)
    markers = [
        ('episode_0', 'AMERICAN FOXY MOMMA (EPISODE 0)', 'hot_scoomp_main'),
        ('spring_break', 'AMERICAN FOXY MOMMA — S04E16:', 'ling_au'),
        ('prequel', 'Hot Scoop: PREQUEL', 'hot_scoomp_main'),
        ('act_1', 'Hot Scoop — ACT ONE:', 'hot_scoomp_main'),
        ('act_2', 'Hot Scoop — ACT TWO:', 'hot_scoomp_main'),
        ('climax_tag', 'Hot Scoop — EPISODE CLIMAX', 'hot_scoomp_main'),
    ]
    boundary_states = {
        'act_1': {'haley':'haley.state.bbl_influencer'},
        'act_2': {'haley':'haley.state.bbl_influencer'},
        'climax_tag': {'haley':'haley.state.bbl_influencer','stella':'stella.state.big_tiddy_steve'},
    }
    starts = []
    for key, heading, canon in markers:
        found = [i for i,line in enumerate(lines) if line.startswith('# ' + heading)]
        if len(found) != 1:
            raise ValueError(f'Expected one heading for {key}, found {len(found)}')
        starts.append(found[0])
    if starts != sorted(starts) or starts[0] != 0:
        raise ValueError('Chronology headings are out of order or omit the beginning')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='timeline-', dir=destination.parent) as temp:
        root = Path(temp)/'project'
        root.mkdir()
        sources = root/'sources'; sources.mkdir()
        shutil.copytree(DEFAULT_CHARACTERS_DIR, root/'characters')
        index = {'schema_version':1, 'description':'Available story and separate outline editions; incomplete.',
                 'sources':{}, 'sections':[],
                 'planned_events':[{'id':'hayley_basement','status':'not written',
                    'after':['jess_event','steve_requests_help']}],
                 'author_exclusions':['main outline beat 11A and related breast-milk storyline']}
        for key, path in files.items():
            target = sources / (key + path.suffix.lower())
            target.write_bytes(raw[key])
            index['sources'][key] = {'original':str(path.resolve()), 'copy':str(target.relative_to(root)),
                                     'sha256':sha256(raw[key])}
        for i, (key, heading, canon) in enumerate(markers):
            start, end = starts[i], starts[i+1] if i+1 < len(starts) else len(lines)
            content = ''.join(lines[start:end]).encode('utf-8')
            story = root/(key + '.md'); story.write_bytes(content)
            manifest = root/(key + '.manifest.json')
            context = copy.deepcopy(EMPTY_MANIFEST)
            if key in boundary_states:
                context['initial_character_states'] = boundary_states[key]
                context['initial_state_provenance'] = {'status':'exercise selection; author review pending',
                    'source':'chronology', 'source_line':start+1,
                    'reason':'Section begins after earlier transformations; state context is not a new transition.'}
            manifest.write_text(json.dumps(context,indent=2)+'\n',encoding='utf-8')
            index['sections'].append({'id':key,'story':story.name,'manifest':manifest.name,'canon':canon,
                'source':'chronology','start_line':start+1,'end_line':end,'sha256':sha256(content)})
        word = word_outline(files['main_docx'], {'11A'})
        main = root/'tapped_out_main.md'; main.write_text(outline_markdown(word),encoding='utf-8',newline='')
        (root/'tapped_out_main.extraction.json').write_text(json.dumps(word,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        main_witness = pdf_outline(files['main_pdf'])
        (root/'tapped_out_main_pdf.extraction.json').write_text(json.dumps(main_witness,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        b_story = pdf_outline(files['b_pdf'])
        b_path = root/'tapped_out_b.md'; b_path.write_text(pdf_outline_markdown(b_story),encoding='utf-8',newline='')
        (root/'tapped_out_b.extraction.json').write_text(json.dumps(b_story,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for key, story, source in [('tapped_out_main',main,'main_docx'),('tapped_out_b',b_path,'b_pdf')]:
            manifest = root/(key + '.manifest.json')
            manifest.write_text(json.dumps(EMPTY_MANIFEST,indent=2)+'\n',encoding='utf-8')
            index['sections'].append({'id':key,'story':story.name,'manifest':manifest.name,'canon':'hot_scoomp_main',
                'source':source,'sha256':sha256(story.read_bytes()),'status':'outline extraction; review required'})
        (root/'timeline.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        root.rename(destination)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--chronology', type=Path)
    mode.add_argument('--workspace', type=Path, help='Existing timeline workspace for a separate Word variant')
    parser.add_argument('--main-docx',type=Path)
    parser.add_argument('--main-pdf',type=Path)
    parser.add_argument('--b-pdf',type=Path)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--variant-docx', type=Path)
    parser.add_argument('--variant-id')
    args = parser.parse_args()
    if args.workspace:
        if not args.variant_docx or not args.variant_id:
            parser.error('--workspace requires --variant-docx and --variant-id')
        if any((args.main_docx, args.main_pdf, args.b_pdf, args.out)):
            parser.error('timeline creation options cannot be combined with --workspace')
        section = add_word_variant(args.workspace, args.variant_docx, args.variant_id)
        print(json.dumps({'workspace':str(args.workspace), 'section':section,
                          'status':'source extraction requires review'}, indent=2))
        return
    if not all((args.main_docx, args.main_pdf, args.b_pdf, args.out)):
        parser.error('--chronology requires --main-docx, --main-pdf, --b-pdf and --out')
    if args.variant_docx or args.variant_id:
        parser.error('--variant-docx and --variant-id require --workspace')
    index = prepare_timeline(args.chronology,args.main_docx,args.main_pdf,args.b_pdf,args.out)
    print(json.dumps({'workspace':str(args.out), 'sections':[s['id'] for s in index['sections']],
                      'status':'source extraction requires review'},indent=2))


if __name__ == '__main__':
    main()
