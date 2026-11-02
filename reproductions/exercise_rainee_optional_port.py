"""Test the optional Rainee intermediate in a separate synthetic data copy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reproductions.audit_timeline_pipeline import Session, copy_section


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.workspace.resolve(), args.out.resolve()
    if out.exists() or out.is_relative_to(source):
        raise ValueError('Choose a new destination outside the source workspace')
    timeline = json.loads((source/'timeline.json').read_text(encoding='utf-8'))
    section = next(s for s in timeline['sections'] if s['id'] == 'gemini_master')
    story, manifest = copy_section(source, out, section)
    before = story.read_bytes()
    data = out/'character_data'
    refs = []
    for suffix in ('a', 'b'):
        name = 'synthetic_rainee_50_' + suffix
        package = {'dataset_id':name, 'revision':'1', 'schema_id':'narrative.behavior.v1',
                   'owner_id':'rainee', 'review_status':'pending_review',
                   'rules':[{'rule_id':'probe', 'event':'synthetic_probe',
                             'response':'SYNTHETIC RAINEE RESPONSE ' + suffix.upper()}]}
        raw = json.dumps(package).encode('utf-8')
        path = data/(name+'.json')
        path.write_bytes(raw)
        refs.append({'dataset_id':name, 'revision':'1', 'domain':'behavior_rules',
                     'schema_id':'narrative.behavior.v1', 'relative_path':path.name,
                     'content_hash':hashlib.sha256(raw).hexdigest()})
    session = Session(story, manifest, out/'characters', section['canon'])
    form_id = 'rainee.state.peter_50'
    port_id = 'port:' + form_id + '.port.data'
    try:
        status, port = session.post('/api/node', id=port_id)
        if status != 200:
            raise ValueError('Optional form port unavailable')
        results = []
        for ref in refs:
            value = dict(port['data'], mode='replace', bindings=[ref])
            status, changed = session.post('/api/node/update', id=port_id, value=json.dumps(value))
            if status != 200:
                raise ValueError('Synthetic port update failed: ' + changed.get('error', 'unknown'))
            status, report = session.post('/api/project', event='synthetic_probe', state_overrides={'rainee':form_id})
            if status != 200:
                raise ValueError('Synthetic recomputation failed: ' + report.get('error', 'unknown'))
            results.append({item['entity']:item for item in report['reactions']})
        first, second = results
        changed = (first['rainee']['candidates'][0]['text'] == 'SYNTHETIC RAINEE RESPONSE A' and
                   second['rainee']['candidates'][0]['text'] == 'SYNTHETIC RAINEE RESPONSE B')
        unrelated = (first['stella']['dependency_hash'] == second['stella']['dependency_hash'] and
                     second['stella']['reused'])
        status, saved = session.post('/api/save')
        if status != 200:
            raise ValueError('Synthetic workspace save failed: ' + saved.get('error', 'unknown'))
        from urllib.request import urlopen
        with urlopen(session.url+'/api/source?reload=1') as response:
            loaded = json.load(response)
        session.text, session.document, session.revision = loaded['text'], loaded['rich_document'], loaded['revision']
        status, trace = session.post('/api/character/trace', id='ent:rainee')
        state = next(item for item in trace.get('states', []) if item['id'] == form_id)
        status2, connected = session.post('/api/data/inspect', id=port_id)
        result = {'synthetic':True, 'form_id':form_id, 'state_availability':state['availability'],
                  'changed_reaction':changed, 'unrelated_stella_reused':unrelated,
                  'reloaded_binding':status2 == 200 and connected['data_input']['mode'] == 'replace' and
                       any(item['dataset_id'] == refs[1]['dataset_id'] for item in connected['records']),
                  'story_unchanged':story.read_bytes() == before,
                  'notice':'Synthetic optional-form behavior for testing only; no story event or personality is approved.'}
        (out/'SYNTHETIC_PORT_EXERCISE.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        if not all(result[key] for key in ('changed_reaction','unrelated_stella_reused','reloaded_binding','story_unchanged')):
            raise ValueError('A synthetic port exercise assertion failed')
    finally:
        session.close()


if __name__ == '__main__':
    main()
