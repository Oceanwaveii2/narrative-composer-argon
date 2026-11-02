"""Exercise one imported Word variant in a disposable copy of the workspace."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_composer.editor import EditorHandler
from narrative_composer.persistence import ignore_recovery_artifacts


def digest(content):
    return hashlib.sha256(content).hexdigest()


def exercise(root, section_id):
    index = json.loads((root / 'timeline.json').read_text(encoding='utf-8'))
    section = next(s for s in index['sections'] if s['id'] == section_id)
    original_story = (root / section['story']).read_bytes()
    source_info = index['sources'][section['source']]
    preserved_source = root / source_info['copy']
    original_word = preserved_source.read_bytes()
    assert digest(original_word) == source_info['sha256']
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory) / 'workspace'
        shutil.copytree(root, work, ignore=ignore_recovery_artifacts)
        server = ThreadingHTTPServer(('127.0.0.1', 0), EditorHandler)
        server.screenplay_path = work / section['story']
        server.manifest_path = work / section['manifest']
        server.entity_dir = work / 'characters'
        server.timeline_path = work / 'timeline.json'
        server.canon = section['canon']
        server.store = None
        server.store_text = None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)

        def post(route, data):
            request = Request(base + route, data=json.dumps(data).encode('utf-8'),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                return json.load(response)

        try:
            with urlopen(base + '/api/source') as response:
                initial = json.load(response)
            text, revision = initial['text'], initial['revision']
            data_dir = work / 'character_data'
            data_dir.mkdir(exist_ok=True)

            def package(name, result):
                record = {'dataset_id': name, 'revision': '1', 'schema_id': 'narrative.behavior.v1',
                          'owner_id': 'stella', 'review_status': 'pending_review',
                          'rules': [{'rule_id': 'fixture', 'event': 'variant_exercise', 'response': result}]}
                content = json.dumps(record).encode('utf-8')
                (data_dir / (name + '.json')).write_bytes(content)
                return {'dataset_id': name, 'revision': '1', 'domain': 'behavior_rules',
                        'schema_id': 'narrative.behavior.v1', 'relative_path': name + '.json',
                        'content_hash': digest(content)}

            first = package('variant_fixture_a', 'SYNTHETIC RESPONSE A')
            second = package('variant_fixture_b', 'SYNTHETIC RESPONSE B')
            port_id = 'port:stella.state.big_tiddy_steve.port.data'
            port = post('/api/node', {'text': text, 'revision': revision, 'id': port_id})['data']
            port.update(mode='replace', bindings=[first])
            revision = post('/api/node/update', {'text': text, 'revision': revision, 'id': port_id,
                                                 'value': json.dumps(port)})['revision']
            scenario = {'text': text, 'revision': revision, 'event': 'variant_exercise',
                        'state_overrides': {'stella': 'stella.state.big_tiddy_steve'}}
            result_a = {r['entity']: r for r in post('/api/project', scenario)['reactions']}
            port['bindings'] = [second]
            revision = post('/api/node/update', {'text': text, 'revision': revision, 'id': port_id,
                                                 'value': json.dumps(port)})['revision']
            scenario['revision'] = revision
            result_b = {r['entity']: r for r in post('/api/project', scenario)['reactions']}
            assert result_a['stella']['candidates'][0]['text'] == 'SYNTHETIC RESPONSE A'
            assert result_b['stella']['candidates'][0]['text'] == 'SYNTHETIC RESPONSE B'
            assert result_b['stella']['state_source'] == 'hypothetical'
            assert result_a['rainee']['dependency_hash'] == result_b['rainee']['dependency_hash']
            assert result_b['rainee']['reused']
            block = next(n for n in server.store.of_kind('block')
                         if n.data['role'] == 'action' and n.data['text'].strip())
            changed = post('/api/node/update', {'text': text, 'revision': revision, 'id': block.id,
                            'value': block.data['text'] + ' [SANDBOX EXERCISE]'})
            edited, revision = changed['text'], changed['revision']
            old_lines, new_lines = text.split('\n'), edited.split('\n')
            assert len(old_lines) == len(new_lines)
            assert sum(a != b for a, b in zip(old_lines, new_lines)) == 1
            assert post('/api/save', {'text': edited, 'revision': revision})['ok']
            with urlopen(base + '/api/source?reload=1') as response:
                reloaded = json.load(response)
            assert reloaded['text'] == edited
            assert (root / section['story']).read_bytes() == original_story
            assert preserved_source.read_bytes() == original_word
            return {'section': section_id, 'scope': 'disposable workspace; synthetic fixture; hypothetical form',
                    'steve_form_port_changed_reaction': True, 'unrelated_rainee_result_reused': True,
                    'one_line_edit_saved_and_reloaded': True, 'real_projection_unchanged': True,
                    'preserved_word_unchanged': True, 'projection_sha256': digest(original_story),
                    'word_source_sha256': digest(original_word)}
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--section', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = exercise(args.workspace.resolve(), args.section)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))
