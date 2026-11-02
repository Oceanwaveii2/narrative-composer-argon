"""Graph copied editions and request bounded, non-explicit Gemini proposals.

Full stories stay local. Gemini receives only one independently reviewed source
block at a time in a separate focus copy, not the surrounding timeline. The
focused composer manifest and empty behavioral bindings are exercise inputs,
not newly established canon. No proposal is applied.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import threading
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_composer.compiler.document import BlockRole
from narrative_composer.gemini_session import GeminiCliSession
from narrative_composer.prose.providers.gemini_flash import ProviderExecutionError
from narrative_composer.store import document_from_store
from reproductions.audit_timeline_pipeline import LIVE_TARGETS, Session, copy_section, digest

# The outline snippets are short, non-explicit source notes, not completed events.
EXTRA = {
    'gemini_master': (21, LIVE_TARGETS['episode_0'][1], ['KELLY'], 'action'),
    'tapped_out_main': (63, '46407078ae304fbc7cb933fa34f66045b5a181eae780660bc12a9dffd5b3eae9', ['FRANCINE', 'STELLA'], 'note'),
    'tapped_out_b': (25, '73fdc58a5e90abd502c460acb0e40ea8ae0840f9350ecf9c9945738721839169', [], 'note'),
}
ACTORS = {'episode_0':['KELLY'], 'spring_break':[], 'prequel':[],
          'act_1':['STELLA'], 'act_2':['FRANCINE', 'STELLA'],
          'climax_tag':['FRANCINE'], 'tapped_out_quick_story':['HALEY']}

# An additional conservative output barrier. This is not a general classifier;
# the source passages were independently reviewed and fixed by hash above.
RESTRICTED = re.compile(r'\b(?:breasts?|boobs?|bust|buttocks?|cleavage|nipples?|lingerie|underwear|panties|sexual|sex|horny|nude|naked|lust|erotic|seduct\w*|arous\w*|orgasm\w*|stripper\w*|titt\w*|tiddy)\b', re.I)
real_call = GeminiCliSession._call
def guarded_call(self, content):
    if RESTRICTED.search(content):
        raise ProviderExecutionError('Request held: the bounded context failed the review filter')
    identity, answer = real_call(self, content)
    if RESTRICTED.search(answer):
        raise ProviderExecutionError('Response held: it failed the review filter')
    return identity, answer
GeminiCliSession._call = guarded_call


def new_focus(case, text, actors, note):
    focus = case / 'focused_review'
    focus.mkdir()
    shutil.copytree(case / 'characters', focus / 'characters')
    # No optional behavioral data is assumed for these bounded exercises.
    for path in (focus / 'characters').glob('*.json'):
        actor = json.loads(path.read_text(encoding='utf-8'))
        actor.get('attributes', {}).pop('personality_profile', None)
        actor.get('attributes', {}).pop('behavior_rules', None)
        if actor.get('data_port'):
            actor['data_port']['bindings'] = []
        for state in actor.get('states', []):
            if state.get('data_port'):
                state['data_port']['bindings'] = []
        path.write_text(json.dumps(actor, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    story = focus / 'source_excerpt.md'
    story.write_text(text + '\n', encoding='utf-8', newline='\n')
    setting = 'source_setting_unspecified'
    beat = {'beat_id':'bounded_source_review', 'chunk_index':1, 'beat_order':1,
            'slugline':'INT. SOURCE SETTING UNSPECIFIED - TIME UNSPECIFIED',
            'active_characters':actors,
            'dramatic_goal':('Treat the following as an outline note, not a confirmed event. ' if note else '') +
                'Produce a brief family-safe version of the following source passage, preserving its actions and '
                'uncertainties. Do not invent events, relationships, physical intimacy, or a setting. '
                'Do not treat this exercise setup as canon. SOURCE PASSAGE: ' + text,
            'state_delta':{}}
    manifest = {'manifest_name':'Bounded review exercise; not canon', 'version':'1',
                'facts':{}, 'props':{}, 'initial_beliefs':{},
                'character_locations':{actor:setting for actor in actors},
                'room_topology':{}, 'beats':{'bounded_source_review':beat}}
    manifest_path = focus / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return focus, story, manifest_path


def inspect_edition(workspace, out, section):
    case = out / 'editions' / section['id']
    story, manifest = copy_section(workspace, case, section)
    before = story.read_bytes()
    session = Session(story, manifest, case/'characters', section['canon'])
    result = {'id':section['id'], 'canon':section['canon'], 'source_file':section['story'],
              'source_sha256':digest(before), 'status':section.get('status', 'story edition')}
    try:
        status, report = session.post('/api/project', event='source_review')
        if status != 200:
            raise RuntimeError('Graph analysis request failed')
        ds = report.get('diagnostics', [])
        result['analysis'] = {'status':report['stages']['analysis'],
            'technical_errors':sum(d.get('severity')=='ERROR' for d in ds),
            'review_questions':sum(bool(d.get('requires_author_review')) for d in ds),
            'rules':dict(Counter(d.get('rule_id', 'unknown') for d in ds if d.get('requires_author_review')))}
        result['actors'] = {}
        for entity in session.server.store.of_kind('entity'):
            code, trace = session.post('/api/character/trace', id=entity.id)
            if code != 200:
                raise RuntimeError('Character trace failed for ' + entity.id)
            actor = trace['entity_id']
            data = json.loads((case/'characters'/(actor+'.json')).read_text(encoding='utf-8'))
            ids = {s['id'] for s in trace['states']}
            transforms = [{'id':t['id'], 'from':t['from_state'], 'to':t['to_state'],
                           'provisional':bool(t.get('provisional', False))}
                          for t in data.get('transforms', [])
                          if t['from_state'] in ids and t['to_state'] in ids
                          and (not t.get('canons') or section['canon'] in t['canons'])]
            result['actors'][actor] = {'name':trace['display_name'], 'base':data.get('base_state'),
                'root_port':data.get('data_port',{}).get('id'),
                'states':trace['states'], 'transforms':transforms,
                'entries':[{'line':e['line'],'block_id':e['block_id'],'kind':e['kind'],
                            'state_id':e.get('state_id'),'line_sha256':e['line_sha256']}
                           for e in trace['entries']],
                'observations':[{'line':e['line'],'state':e['state'],'kind':e['kind'],
                                 'reviewed':e['reviewed'],'block_ids':e['block_ids']}
                                for e in trace['observations']]}
        target = EXTRA.get(section['id'])
        if not target and section['id'] in LIVE_TARGETS:
            line, expected = LIVE_TARGETS[section['id']]
            target = (line, expected, ACTORS[section['id']], 'action')
        if target:
            line, expected, actors, role = target
            selected = [b for b in document_from_store(session.server.store).blocks
                        if b.line == line and b.role.value == role and digest(b.text.encode('utf-8')) == expected]
            if len(selected) != 1 or RESTRICTED.search(selected[0].text):
                result['target_error'] = 'Pre-reviewed source block changed or failed the review filter.'
            else:
                b=selected[0]
                result['target']={'line':line, 'block_id':b.id, 'sha256':expected, 'role':role,
                                  'original':b.text, 'active_actors':actors}
        result['copy_unchanged']=story.read_bytes() == before
    finally:
        session.close()
    return result


def run_focus(case, section, result):
    target=result.get('target')
    if not target:
        return {'error':result.get('target_error', 'No bounded source passage selected')}
    focus, story, manifest = new_focus(case, target['original'], target['active_actors'], target['role']=='note')
    before=story.read_bytes()
    session=Session(story, manifest, focus/'characters', section['canon'])
    session.server.gemini_state_dir = focus/'gemini_session'
    answer={}
    try:
        if target['role'] == 'action':
            blocks=[b for b in document_from_store(session.server.store).blocks if b.role == BlockRole.ACTION]
            if len(blocks)!=1:
                answer['conditioner']={'status':'not run: focus block was not uniquely parsed'}
            else:
                code, data=session.post('/api/condition', provider='gemini_session', limit=1,
                                        target_block_ids=[blocks[0].id])
                patches=data.get('patches', [])
                answer['conditioner']={'http':code, 'proposals':patches,
                    'status':'review required' if any(p.get('eligible') for p in patches) else
                             'held or unavailable', 'error':data.get('error')}
        else:
            answer['conditioner']={'status':'not supported for outline notes', 'proposals':[]}
        code, data=session.post('/api/compose', provider='gemini_session', beat_id='bounded_source_review')
        patches=data.get('patches', [])
        answer['composer']={'http':code, 'proposals':patches,
            'status':'review required' if any(p.get('eligible') for p in patches) else
                     'held or unavailable', 'error':data.get('error')}
        answer['focus_source_unchanged']=story.read_bytes()==before
        answer['scope']='bounded source block and copied character definitions; no full edition sent'
    finally:
        session.close()
    return answer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=3)
    args=parser.parse_args()
    workspace=args.workspace.resolve()
    out=args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'editions').mkdir()
    index=json.loads((workspace/'timeline.json').read_text(encoding='utf-8'))
    baseline=json.loads((workspace/'INPUT_BASELINE.json').read_text(encoding='utf-8'))
    before={entry['path']:digest(Path(entry['path']).read_bytes()) for entry in baseline['original_inputs']}
    result={'created_utc':datetime.now(timezone.utc).isoformat(), 'provider':'gemini_session',
            'workspace':str(workspace), 'editions':[], 'limitations':[
                'Graph analyzes copied complete editions; Gemini receives only the selected bounded source passages.',
                'Behavioral bindings are empty in focused exercises; no personality records are invented.',
                'Outline notes are not completed events and do not support action-paragraph conditioning.',
                'Proposals are suggestions only and remain pending author review.'],
            'original_hashes_before':before}
    for section in index['sections']:
        try:
            row=inspect_edition(workspace, out, section)
        except Exception as exc:
            row={'id':section['id'], 'error':f'{type(exc).__name__}: {exc}'}
        result['editions'].append(row)
        print('GRAPH',section['id'],row.get('analysis',{}).get('status','failed'),flush=True)
    result_path=out/'results.json'
    def save():
        tmp=result_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        tmp.replace(result_path)
    save()
    by_id={s['id']:s for s in index['sections']}
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,3))) as pool:
        jobs={pool.submit(run_focus,out/'editions'/row['id'],by_id[row['id']],row):row
              for row in result['editions'] if row.get('target')}
        for future in as_completed(jobs):
            row=jobs[future]
            try:
                row['live']=future.result()
            except Exception as exc:
                row['live']={'error':f'{type(exc).__name__}: {exc}'}
            print('GEMINI',row['id'],row['live'].get('conditioner',{}).get('status','unavailable'),
                  '/',row['live'].get('composer',{}).get('status','unavailable'),flush=True)
            save()
    after={path:digest(Path(path).read_bytes()) if Path(path).is_file() else None for path in before}
    result['original_hashes_unchanged']=all(after[path]==before[path] for path in before)
    result['original_hash_count']=len(before)
    result['completed_utc']=datetime.now(timezone.utc).isoformat()
    save()
    print('DONE originals unchanged:',result['original_hashes_unchanged'],'count',len(before),flush=True)

if __name__=='__main__':
    main()
