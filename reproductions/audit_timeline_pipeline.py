"""Run a review-only timeline audit using disposable copies and bounded model targets.

The selected target hashes correspond to manually inspected, non-explicit action
passages. A changed passage or nonempty world context is not sent to a live provider. Original
files and path-bearing recovery journals are never opened for writing.
"""
import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import threading
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_composer.compiler.document import BlockRole
from narrative_composer.editor import EditorHandler
from narrative_composer.persistence import ignore_recovery_artifacts
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.rich_document import new_document, normalized, validate_document
from narrative_composer.store import document_from_store, to_text


LIVE_TARGETS = {
    'episode_0': (21, '48999ff00350cc69f4a254f59c65d31a67c747b14ab5a7590f153a4732e6f974'),
    'spring_break': (185, 'af222c7623c1996c1ebef967a926a037eeb2a5b16c97180582bda7c06291ae4c'),
    'prequel': (129, '1eeeee91142fe450950df093fa362575da1a01b2216730410ec546bd114437a2'),
    'act_1': (274, 'd307256b3923827fdcddb59e324f98f4426389a7891d942727a1ba37c792de52'),
    'act_2': (405, 'd8771f7b2cc9c5bc1b02d7dea615e54b0e425bf6feffe69ff2fadde82159d056'),
    'climax_tag': (109, '656aec9bceda397747fae4535a6c30e0049e2dceb0baa1cd07933833b6426ca0'),
    'tapped_out_quick_story': (38, '6c1582b7ba04ba2795f8b5bfefc7e8dd95ffe5c9e659ea7877e539e4648ddf1e'),
}

REQUIRED_FORMS = {
    'rainee': ['base', 'madonna', 'christie_brinkley', 'heather_locklear', 'kim_basinger',
               'debbie_harry', 'bo_derek', 'peter_50', 'peter'],
    'stella': ['standard', 'nerd_20', 'nerd_40', 'nerd_70', 'big_tiddy_steve'],
    'haley': ['standard', 'roger_dome', 'bbl_influencer'],
    'francine': ['base', 'nurse_deluxe', 'jlo_bbl'],
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(root, index):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Timeline workspace contains a symlink; it cannot be safely copied')
        if path.is_file():
            files['workspace/' + path.relative_to(root).as_posix()] = digest(path.read_bytes())
    for source_id, source in index.get('sources', {}).items():
        original = Path(source.get('original', ''))
        if original.is_file() and original.suffix.lower() in ('.md', '.docx', '.pdf'):
            files['original/' + source_id] = digest(original.read_bytes())
    return files


def copy_section(workspace, case, section):
    case.mkdir()
    story = workspace / section['story']
    for source in (story, story.with_suffix(story.suffix + '.ids.json'),
                   story.with_suffix(story.suffix + '.rich.json'), story.with_suffix('.extraction.json')):
        if source.is_file():
            shutil.copy2(source, case / source.name)
    shutil.copy2(workspace / section['manifest'], case / section['manifest'])
    shutil.copytree(workspace / 'characters', case / 'characters', ignore=ignore_recovery_artifacts)
    if (workspace / 'character_data').is_dir():
        shutil.copytree(workspace / 'character_data', case / 'character_data', ignore=ignore_recovery_artifacts)
    return case / story.name, case / section['manifest']


class Session:
    def __init__(self, story, manifest, characters, canon):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), EditorHandler)
        self.server.screenplay_path, self.server.manifest_path = story, manifest
        self.server.entity_dir, self.server.canon = characters, canon
        self.server.codex_state_dir = story.parent / '.codex_test_sessions'
        self.server.store, self.server.store_text = None, None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        with urlopen(self.url + '/api/source') as response:
            self.initial = json.load(response)
        self.text = self.initial['text']
        self.document = self.initial['rich_document']
        self.revision = self.initial['revision']

    def post(self, route, **values):
        payload = {'text': self.text, 'revision': self.revision, 'rich_document': self.document, **values}
        request = Request(self.url + route, data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=400) as response:
                status, body = response.status, json.load(response)
        except HTTPError as exc:
            status, body = exc.code, json.load(exc)
        if status == 200 and body.get('revision'):
            self.revision = body['revision']
        return status, body

    def close(self):
        self.server.shutdown()
        if hasattr(self.server, 'codex_session'):
            self.server.codex_session.close()
        self.server.server_close()
        self.thread.join(timeout=5)


def append_document(document, original, updated):
    old, new = normalized(original), normalized(updated)
    if not new.startswith(old):
        raise ValueError('Composer changed existing text')
    result = copy.deepcopy(document)
    parts = new[len(old):].split('\n')
    if parts[0]:
        result['content'][-1].setdefault('content', []).append({'type': 'text', 'text': parts[0]})
    for line in parts[1:]:
        result['content'].extend(new_document(line)['content'])
    validate_document(result, updated)
    return result


def inspect_case(workspace, case, section, live_venice, live_codex, graph_out=None):
    story, manifest = copy_section(workspace, case, section)
    before = story.read_bytes()
    context = json.loads(manifest.read_text(encoding='utf-8'))
    session = Session(story, manifest, case / 'characters', section['canon'])
    result = {'id': section['id'], 'canon': section['canon'], 'rich_status': session.initial['rich_status'],
              'source_sha256': digest(before), 'actual_beat_count': len(context.get('beats', {}))}
    candidates = []
    try:
        assert session.text.encode('utf-8') == before and to_text(session.server.store) == session.text
        status, project = session.post('/api/project', event='audit_observe')
        if status != 200:
            raise ValueError('Project analysis failed: ' + project.get('error', 'unknown'))
        diagnostics = Counter(d['rule_id'] for d in project['diagnostics'] if d['severity'] == 'ERROR')
        result['analysis'] = {'status': project['stages']['analysis'], 'errors': sum(diagnostics.values()),
                              'error_rules': dict(diagnostics), 'coverage': project['coverage'],
                              'findings': [d for d in project['diagnostics'] if d['severity'] == 'ERROR'],
                              'review_questions': [d for d in project['diagnostics']
                                                   if d.get('classification') == 'author_review_question']}
        result['character_trace'] = {}
        for actor in session.server.store.of_kind('entity'):
            trace_status, trace = session.post('/api/character/trace', id=actor.id)
            if trace_status != 200:
                raise ValueError('Character trace failed: ' + trace.get('error', 'unknown'))
            result['character_trace'][trace['entity_id']] = {
                'edition':trace['edition'], 'source_sha256':trace['source_sha256'],
                'source_blocks':len(trace['entries']),
                'source_block_kinds':dict(Counter(item['kind'] for item in trace['entries'])),
                'states':trace['states'], 'observations':len(trace['observations'])}
        result['data_ports'] = {item['entity']:{'status':item['data_input']['status'],
            'capabilities':item['data_input'].get('capabilities', []),
            'source_evidence':{k:v for k,v in item['source_evidence'].items() if k != 'verified_references'},
            'reaction_status':item['status']} for item in project['reactions']}
        required = [f'port:{actor}.port.data' for actor in REQUIRED_FORMS]
        required += [f'port:{actor}.state.{form}.port.data'
                     for actor, forms in REQUIRED_FORMS.items() for form in forms]
        missing = [identity for identity in required if identity not in session.server.store.nodes]
        result['character_ports'] = {'required': len(required), 'missing': missing}
        status, graph = session.post('/api/graph')
        result['graph_http'] = status
        if status == 200 and graph_out is not None:
            graph_path = graph_out / (section['id'] + '.html')
            with graph_path.open('x', encoding='utf-8') as stream:
                stream.write(graph['html'])
            result['graph_artifact'] = str(graph_path)
        # The viewer embeds the data port's ID without the store's "port:" node prefix.
        result['graph_has_steve_form_port'] = status == 200 and 'stella.state.big_tiddy_steve.port.data' in graph['html']
        status, mock = session.post('/api/condition', provider='mock', limit=1)
        result['mock_conditioner'] = {'http': status, 'proposals': len(mock.get('patches', [])),
                                      'eligible': sum(p.get('eligible', False) for p in mock.get('patches', []))}
        status, compose = session.post('/api/compose', provider='mock')
        result['actual_composer'] = {'http': status, 'proposals': len(compose.get('patches', [])),
                                     'reason': compose.get('error') if status != 200 else 'pending review'}
        target = LIVE_TARGETS.get(section['id'])
        for provider, enabled in [('venice', live_venice), ('codex', live_codex)]:
            if not enabled:
                result[provider] = {'status': 'not run'}
            elif not target:
                result[provider] = {'status': 'not applicable: no pre-reviewed action target'}
            elif any(context.get(k) for k in ('facts', 'props', 'initial_beliefs')):
                result[provider] = {'status': 'skipped: world context changed; review before sending'}
            else:
                line, expected_hash = target
                selected = [b for b in document_from_store(session.server.store).blocks
                            if b.line == line and b.role == BlockRole.ACTION and digest(b.text.encode('utf-8')) == expected_hash]
                if len(selected) != 1 or not ProseDiagnosticsAnalyzer.analyze(selected[0].text).warnings:
                    result[provider] = {'status': 'skipped: pre-reviewed target changed or is not flagged'}
                    continue
                status, data = session.post('/api/condition', provider=provider, limit=1,
                                            target_block_ids=[selected[0].id])
                patches = data.get('patches', [])
                if status == 200 and len(patches) == 1:
                    candidate = {'section': section['id'], 'source_line': line, **patches[0]}
                    candidates.append(candidate)
                    result[provider] = {'status': 'pending author review' if candidate.get('eligible') else 'rejected',
                        'http': status, 'provider_returned_text': bool(candidate.get('proposed')),
                        'reason': candidate.get('reason'), 'attempt_count': candidate.get('attempt_count'),
                        'attempt_reasons': candidate.get('attempt_reasons', []), 'applied': False,
                        'model_name': candidate.get('model_name'), 'reasoning_effort': candidate.get('reasoning_effort')}
                else:
                    result[provider] = {'status': 'request failed', 'http': status}
        result['planning_left_copy_unchanged'] = story.read_bytes() == before and to_text(session.server.store) == session.text
    finally:
        session.close()
    return result, candidates


def exercise_case(case, section):
    story = case / section['story']
    manifest = case / section['manifest']
    original = story.read_bytes()
    context = json.loads(manifest.read_text(encoding='utf-8'))
    beat_id = 'audit_hypothetical_beat'
    if beat_id in context.setdefault('beats', {}):
        raise ValueError('Synthetic beat ID already exists')
    context['beats'][beat_id] = {'beat_id': beat_id, 'chunk_index': 1, 'beat_order': 1,
        'slugline': 'INT. ROOM - DAY', 'active_characters': ['STELLA'],
        'dramatic_goal': 'A character pauses to consider the situation.', 'state_delta': {}}
    manifest.write_text(json.dumps(context, indent=2) + '\n', encoding='utf-8')
    data_dir = case / 'character_data'
    data_dir.mkdir(exist_ok=True)
    refs = []
    for suffix in ('a', 'b'):
        name = 'audit_fixture_' + suffix
        path = data_dir / (name + '.json')
        if path.exists():
            raise FileExistsError('Synthetic data fixture already exists')
        record = {'dataset_id': name, 'revision': '1', 'schema_id': 'narrative.behavior.v1',
                  'owner_id': 'stella', 'review_status': 'pending_review',
                  'rules': [{'rule_id': 'audit', 'event': beat_id, 'response': 'SYNTHETIC RESPONSE ' + suffix.upper()}]}
        raw = json.dumps(record).encode('utf-8')
        path.write_bytes(raw)
        refs.append({'dataset_id': name, 'revision': '1', 'domain': 'behavior_rules',
                     'schema_id': 'narrative.behavior.v1', 'relative_path': path.name, 'content_hash': digest(raw)})
    session = Session(story, manifest, case / 'characters', section['canon'])
    try:
        form = 'poser_nerd' if section['canon'] == 'ling_au' else 'big_tiddy_steve'
        form_id = 'stella.state.' + form
        port_id = 'port:' + form_id + '.port.data'
        state_status, appearances = session.post('/api/state/appearances', id='st:' + form_id)
        status, port = session.post('/api/node', id=port_id)
        if status != 200:
            raise ValueError('Form data port unavailable')
        port_data = port['data']
        results = []
        for ref in refs:
            port_data.update(mode='replace', bindings=[ref])
            status, edited = session.post('/api/node/update', id=port_id, value=json.dumps(port_data))
            if status != 200:
                raise ValueError('Could not bind synthetic data: ' + edited.get('error', 'unknown'))
            status, project = session.post('/api/project', event=beat_id, state_overrides={'stella': form_id})
            if status != 200:
                raise ValueError('Synthetic recomputation failed')
            results.append({r['entity']: r for r in project['reactions']})
        a, b = results
        changed = (a['stella']['candidates'][0]['text'] == 'SYNTHETIC RESPONSE A' and
                   b['stella']['candidates'][0]['text'] == 'SYNTHETIC RESPONSE B')
        unrelated = a['rainee']['dependency_hash'] == b['rainee']['dependency_hash'] and b['rainee']['reused']
        assert story.read_bytes() == original
        condition_status, conditioning = session.post('/api/condition', provider='mock', limit=1)
        condition_patches = conditioning.get('patches', [])
        status, composition = session.post('/api/compose', provider='mock', beat_id=beat_id)
        result = {'form': form_id, 'data': 'synthetic; hypothetical', 'reaction_changed': changed,
                  'unrelated_rainee_reused': unrelated, 'mock_composer_http': status,
                  'state_appearances_http': state_status,
                  'state_appearances_detected':len(appearances.get('appearances', [])),
                  'conditioner': {'http':condition_status, 'proposal_count':len(condition_patches),
                     'eligible':sum(bool(p.get('eligible')) for p in condition_patches),
                     'review':'mock proposals held for author review; no semantic approval',
                     'proposals':[{'line':p.get('line'), 'eligible':p.get('eligible'),
                                   'reason':p.get('reason'), 'proposal_id':p.get('proposal_id')} for p in condition_patches]}}
        if status != 200 or not composition.get('patches'):
            result['composer_status'] = composition.get('error', 'no proposal')
            return result
        proposal = composition['patches'][0]
        status, preview = session.post('/api/proposal/apply', proposal_id=proposal['proposal_id'],
                                       reviewed=True, preview_only=True)
        if status != 200:
            result['composer_status'] = 'preview rejected: ' + preview.get('error', 'unknown')
            return result
        rich_after = append_document(session.document, session.text, preview['text'])
        status, applied = session.post('/api/proposal/apply', proposal_id=proposal['proposal_id'], reviewed=True)
        if status != 200 or applied.get('text') != preview['text']:
            result['composer_status'] = 'apply failed or differed from preview'
            return result
        session.text, session.document = applied['text'], rich_after
        status, saved = session.post('/api/save')
        if status != 200:
            result['composer_status'] = 'save failed: ' + saved.get('error', 'unknown')
            return result
        with urlopen(session.url + '/api/source?reload=1') as response:
            reloaded = json.load(response)
        result.update(composer_status='simulated acceptance in disposable copy',
                      prior_text_preserved=reloaded['text'].startswith(original.decode('utf-8')),
                      rich_document_reloaded=reloaded['rich_document'] == rich_after)
        return result
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--live-venice', action='store_true')
    parser.add_argument('--live-codex', action='store_true')
    args = parser.parse_args()
    source = args.workspace.resolve()
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(source):
        raise ValueError('Choose a new output directory outside the source workspace')
    index = json.loads((source / 'timeline.json').read_text(encoding='utf-8'))
    for section in index['sections']:
        if not re.fullmatch(r'[a-z][a-z0-9_]*', section['id']):
            raise ValueError('Unsafe timeline section ID')
        for key in ('story', 'manifest'):
            path = (source / section[key]).resolve()
            if not path.is_relative_to(source) or not path.is_file() or path.parent != source:
                raise ValueError('Timeline sections must refer to files in the workspace root')
    before = snapshot(source, index)
    out.mkdir(parents=True)
    graph_out = out / 'graphs'
    graph_out.mkdir()
    workspace = out / 'sandbox'
    shutil.copytree(source, workspace, ignore=ignore_recovery_artifacts)
    report = {'workspace': str(source), 'sandbox': str(workspace), 'sections': [],
              'live_scope': 'at most one manually reviewed short action per selected section',
              'synthetic_exercises_are_not_canon': True}
    candidates = []
    temporary = out / 'exercise_cases'
    temporary.mkdir()
    for section in index['sections']:
        case = temporary / section['id']
        try:
            result, selected_candidates = inspect_case(workspace, case, section, args.live_venice, args.live_codex, graph_out)
            candidates.extend(selected_candidates)
            try:
                result['hypothetical'] = exercise_case(case, section)
            except Exception as exc:
                result['hypothetical'] = {'exercise_error': str(exc)}
        except Exception as exc:
            result = {'id': section['id'], 'audit_error': str(exc)}
        report['sections'].append(result)
        (out / 'audit.partial.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('Processed', section['id'], 'error:', result.get('audit_error', 'none'), flush=True)
    after = snapshot(source, index)
    report['source_files_unchanged'] = before == after
    report['changed_source_paths'] = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    report['source_file_count'] = len(before)
    (out / 'provider_proposals.json').write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (out / 'audit_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Original source files unchanged:', report['source_files_unchanged'], flush=True)
    print('Report:', out / 'audit_report.json', flush=True)


if __name__ == '__main__':
    main()
