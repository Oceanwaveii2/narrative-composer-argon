"""Exercise the actual timeline in an isolated copy; never modify source files."""
import argparse
import hashlib
import json
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_composer.editor import EditorHandler
from narrative_composer.graph.registry import load_registry
from narrative_composer.store import build_store, summary, to_text
from narrative_composer.persistence import ignore_recovery_artifacts


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(root: Path):
    index = json.loads((root/'timeline.json').read_text(encoding='utf-8'))
    sections = index['sections']
    assembled = b''.join((root/s['story']).read_bytes() for s in sections if s['source']=='chronology')
    assert assembled == (root/index['sources']['chronology']['copy']).read_bytes(), 'Chronology segments changed source bytes'
    word = json.loads((root/'tapped_out_main.extraction.json').read_text(encoding='utf-8'))
    excluded = [p for p in word['paragraphs'] if p['beat']=='11A' and p['text'].strip()]
    assert excluded and all(not p['included'] for p in excluded), 'Author-excluded beat was included'
    assert 'Beat 11A' not in (root/'tapped_out_main.md').read_text(encoding='utf-8')
    report = {'source_bytes_preserved':True, 'excluded_beat_paragraphs':[p['paragraph'] for p in excluded],
              'sections':[], 'planned_basement':'not written', 'recomputation':{}, 'authoring':{}}
    registry = load_registry(root/'characters')
    for section in sections:
        source, manifest = root/section['story'], root/section['manifest']
        text = source.read_bytes().decode('utf-8')
        store = build_store(source,manifest,canon=section['canon'],registry=registry,use_cache=False)
        assert to_text(store) == text, 'Text projection changed source in ' + section['id']
        metrics = summary(store)
        marker_counts = Counter(o['state'] for o in store.meta['run_graph']['observations']
                                if o['kind']=='state_marker' and o['entity']=='stella')
        cue_counts = Counter(o['state'] for o in store.meta['run_graph']['observations']
                             if o['kind']=='cue_assertion' and o['entity']=='rainee')
        report['sections'].append({'id':section['id'],'canon':section['canon'],
            'bytes':len(source.read_bytes()),'blocks':metrics['kinds'].get('block',0),
            'diagnostics':metrics['diagnostics'],'errors':metrics['errors'],
            'stella_markers':dict(marker_counts),'rainee_form_cues':dict(cue_counts),
            'analysis_scope':'modeled graph checks only; source/meaning require review'})
        print('Processed',section['id'],flush=True)
    act2 = next(s for s in report['sections'] if s['id']=='act_2')
    assert all(act2['stella_markers'].get(s,0) for s in ('nerd_20','nerd_40','nerd_70','big_tiddy_steve'))
    episode = next(s for s in report['sections'] if s['id']=='episode_0')
    assert all(episode['rainee_form_cues'].get(s,0) for s in
               ('madonna','christie_brinkley','heather_locklear','kim_basinger','debbie_harry','bo_derek'))

    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)/'workspace'
        shutil.copytree(root,work,ignore=ignore_recovery_artifacts)
        exercise_manifest = work/'act_2.manifest.json'
        context = json.loads(exercise_manifest.read_text(encoding='utf-8'))
        context['beats']['exercise']={'beat_id':'exercise','chunk_index':1,'beat_order':1,
            'slugline':'INT. LIVING ROOM - CONTINUOUS','active_characters':['STELLA','HAYLEY'],
            'dramatic_goal':'A character pauses to consider the situation.', 'state_delta':{}}
        exercise_manifest.write_text(json.dumps(context,indent=2)+'\n',encoding='utf-8')
        server = ThreadingHTTPServer(('127.0.0.1',0),EditorHandler)
        server.screenplay_path=work/'act_2.md'; server.manifest_path=work/'act_2.manifest.json'
        server.entity_dir=work/'characters'; server.canon='hot_scoomp_main'; server.store=None; server.store_text=None
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        url = 'http://127.0.0.1:' + str(server.server_port)
        def post(route, value):
            request = Request(url+route,data=json.dumps(value).encode('utf-8'),headers={'Content-Type':'application/json'})
            with urlopen(request) as response: return json.load(response)
        try:
            with urlopen(url+'/api/source') as response: initial=json.load(response)
            text, revision = initial['text'], initial['revision']
            before = post('/api/project',{'text':text,'revision':revision,'event':'exercise'})
            before_actors = {r['entity']:r for r in before['reactions']}
            data_dir=work/'character_data'; data_dir.mkdir()
            def package(name, response):
                record={'dataset_id':name,'revision':'1','schema_id':'narrative.behavior.v1',
                        'owner_id':'stella','review_status':'pending_review',
                        'rules':[{'rule_id':'fixture','event':'exercise','response':response}]}
                content=json.dumps(record).encode('utf-8'); (data_dir/(name+'.json')).write_bytes(content)
                return {'dataset_id':name,'revision':'1','domain':'behavior_rules','schema_id':'narrative.behavior.v1',
                        'relative_path':name+'.json','content_hash':sha(content)}
            first, second = package('fixture_a','FIXTURE REACTION A'),package('fixture_b','FIXTURE REACTION B')
            port_id='port:stella.state.big_tiddy_steve.port.data'
            port=post('/api/node',{'text':text,'revision':revision,'id':port_id})['data']
            port.update(mode='replace',bindings=[first])
            updated=post('/api/node/update',{'text':text,'revision':revision,'id':port_id,'value':json.dumps(port)})
            revision=updated['revision']
            scenario={'text':text,'revision':revision,'event':'exercise',
                      'state_overrides':{'stella':'stella.state.big_tiddy_steve'}}
            first_report=post('/api/project',scenario)
            first_actors={r['entity']:r for r in first_report['reactions']}
            assert first_actors['stella']['candidates'][0]['text']=='FIXTURE REACTION A'
            port['bindings']=[second]
            updated=post('/api/node/update',{'text':text,'revision':revision,'id':port_id,'value':json.dumps(port)})
            revision=updated['revision'];scenario['revision']=revision
            second_report=post('/api/project',scenario)
            actors={r['entity']:r for r in second_report['reactions']}
            assert actors['stella']['candidates'][0]['text']=='FIXTURE REACTION B'
            assert actors['stella']['state_source']=='hypothetical'
            assert actors['rainee']['dependency_hash']==before_actors['rainee']['dependency_hash']
            assert actors['rainee']['reused']
            assert server.screenplay_path.read_bytes().decode('utf-8')==text
            report['recomputation']={'actor':'stella','form':'stella.state.big_tiddy_steve',
                'scenario':'hypothetical', 'input':'synthetic test data, not Deep Character data',
                'replaced_port_changed_reaction':True,'unrelated_rainee_result_reused':True,'story_unchanged':True}
            observed = []
            before_review_errors = sum(d['severity']=='ERROR' for d in server.store.meta['diagnostics'])
            for state in ('nerd_20','nerd_40','nerd_70','big_tiddy_steve'):
                nodes = post('/api/nodes',{'text':text,'revision':revision})
                observation = next(o for o in nodes['observations'] if o['kind']=='state_marker'
                                   and o['entity']=='stella' and o['state']==state and not o['accepted'])
                selected = post('/api/observation/accept',{'text':text,'revision':revision,**observation,'reviewed':True})
                revision=selected['revision']; observed.append(state)
            latest = [s for s in server.store.meta['run_graph']['state_instances'] if s['entity']=='stella'][-1]
            assert latest['state_id']=='stella.state.big_tiddy_steve' and latest['source']=='reviewed'
            report['state_review']={'reviewer':'simulated in isolated copy', 'forms':observed,
                'latest_reviewed_form':latest['state_id'], 'transition_causes':'pending review',
                'errors_before':before_review_errors,
                'errors_after':sum(d['severity']=='ERROR' for d in server.store.meta['diagnostics'])}
            repair=post('/api/recook',{'text':text,'revision':revision,'provider':'mock'})
            assert server.screenplay_path.read_bytes().decode('utf-8')==text
            conditioning=post('/api/condition',{'text':text,'revision':revision,'provider':'mock'})
            assert server.screenplay_path.read_bytes().decode('utf-8')==text
            composed=post('/api/compose',{'text':text,'revision':revision,'provider':'mock'})
            assert composed['patches'] and composed['patches'][0]['decision']=='pending review'
            assert server.screenplay_path.read_bytes().decode('utf-8')==text
            report['proposal_paths']={'repair_candidates':len(repair['patches']),
                'conditioning_candidates':len(conditioning['patches']),
                'composition':'synthetic beat and mock provider; pending review', 'story_unchanged':True}
            block=next(n for n in server.store.of_kind('block') if n.data['role']=='action' and n.data['text'].strip())
            before_lines=text.split('\n')
            edited=post('/api/node/update',{'text':text,'revision':revision,'id':block.id,
                'value':block.data['text']+' [EXERCISE EDIT]'})
            changed=edited['text']; revision=edited['revision']
            changed_lines=changed.split('\n')
            assert len(before_lines)==len(changed_lines)
            assert sum(a!=b for a,b in zip(before_lines,changed_lines))==1
            saved=post('/api/save',{'text':changed,'revision':revision})
            assert saved['ok']
            with urlopen(url+'/api/source?reload=1') as response: reloaded=json.load(response)
            assert reloaded['text']==changed and block.id in server.store.nodes
            report['authoring']={'isolated_copy':True,'changed_source_lines':1,'block_id_survived_save_reload':True,
                                  'source_original_untouched':True}
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.workspace)
    if args.out.exists():
        raise FileExistsError('Choose a new report path')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Report written:',args.out)


if __name__=='__main__':
    main()
