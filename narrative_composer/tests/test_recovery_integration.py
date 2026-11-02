"""Behavioral recovery checks on fixed fixtures and the actual HTTP editor.

These assert author-facing guarantees, including failure paths; they do not read
or mutate the real screenplay or contact a provider.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from narrative_composer.editor import EditorHandler, apply_node_edit, save_workspace, restore_browser_newlines
from narrative_composer.store import build_store, registry_from_store, set_block_text, to_text, NodeStore, clear_build_cache
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.pipeline import build_network_for_text, cook_network_to_report
from narrative_composer.condition import plan_conditioning, apply_proposals, _review_html
from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.identity import entries_from_document, save_entries, sidecar_path
from narrative_composer.workspace import project_report
from narrative_composer.persistence import (commit_files, file_hash, WorkspaceConflict,
                                            ignore_recovery_artifacts, recover_transactions)

FIXTURE = Path(__file__).parent / 'fixtures' / 'recovery_project'


class Provider:
    def __init__(self, text=None): self.text = text
    def generate_rewrite(self, request, prompt):
        self.request = request
        return self.text or request.original_text + ' A cold draft moves past.'


class TestRecoveryIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        shutil.copytree(FIXTURE, self.root)
        self.source = self.root / 'story.md'
        self.manifest = self.root / 'manifest.json'
        self.registry = load_registry(self.root / 'characters')
        self.text = self.source.read_text(encoding='utf-8')

    def store(self, text=None, **kwargs):
        return build_store(self.source, self.manifest, canon='recovery', registry=self.registry,
                           text=self.text if text is None else text, use_cache=False, **kwargs)

    def test_every_block_belongs_to_one_scene_and_invalid_graphs_fail(self):
        store = self.store()
        blocks = {n.id for n in store.of_kind('block')}
        links = [e.dst for e in store.edges if e.type == 'has_block']
        self.assertEqual(blocks, set(links))
        self.assertEqual(len(blocks), len(links))
        with self.assertRaises(ValueError): store.add_node(next(iter(blocks)), 'block')
        with self.assertRaises(ValueError): store.add_edge('bad', 'missing', next(iter(blocks)))

    def test_inline_edits_and_leading_blank_offsets_survive(self):
        text = '\n\nINT. HALL - DAY\n\n**DANA:** "Dana waits."\n'
        store = self.store(text)
        cue = next(n for n in store.of_kind('block') if n.data['role'] == 'cue')
        dialogue = next(n for n in store.of_kind('block') if n.data['role'] == 'dialogue')
        set_block_text(store, cue.id, 'ALEX')
        set_block_text(store, dialogue.id, '"Alex waits."')
        self.assertEqual(to_text(store), '\n\nINT. HALL - DAY\n\n**ALEX:** "Alex waits."\n')

    def test_browser_newline_normalization_preserves_original_and_untouched_lines(self):
        original='First\r\nSecond\nThird\r\n'
        self.assertEqual(restore_browser_newlines(original,'First\nSecond\nThird\n'),original)
        self.assertEqual(restore_browser_newlines(original,'First\nEdited\nThird\n'),
                         'First\r\nEdited\nThird\r\n')
        self.assertEqual(restore_browser_newlines('First\r\nLast','First\nInserted\nLast'),
                         'First\r\nInserted\r\nLast')

    def test_nondefault_and_future_fields_roundtrip(self):
        self.registry['dana'].states[1].status = 'deprecated'
        self.registry['dana'].transforms[0].status = 'deprecated'
        self.registry['dana'].model_extra['future_profile'] = {'version':7}
        result = registry_from_store(self.store())['dana']
        self.assertEqual(result.states[1].status, 'deprecated')
        self.assertEqual(result.states[1].voice_profile, 'measured')
        self.assertEqual(result.transforms[0].status, 'deprecated')
        self.assertEqual(result.model_extra['future_profile']['version'], 7)

    def test_invalid_identity_is_rejected_without_poisoning_session(self):
        store = self.store()
        before = store.to_dict()
        data = copy.deepcopy(store.node('ent:dana').data)
        del data['entity_id']
        with self.assertRaises(ValueError): apply_node_edit(store, 'ent:dana', json.dumps(data))
        self.assertEqual(store.to_dict(), before)

    def test_character_replacement_recomputes_only_affected_actor(self):
        store, cache = self.store(), {}
        first = project_report(store, cache=cache)
        before_alex = next(r for r in first['reactions'] if r['entity']=='alex')
        data = copy.deepcopy(store.node('ent:dana').data)
        data['attributes']['profile_version'] = 'assertive-2'
        data['attributes']['behavior_rules'][0]['response'] = 'Dana asks Alex for a clear answer.'
        apply_node_edit(store, 'ent:dana', json.dumps(data))
        self.registry = registry_from_store(store)
        updated = project_report(self.store(), cache=cache)
        actors = {r['entity']:r for r in updated['reactions']}
        self.assertFalse(actors['dana']['reused'])
        self.assertTrue(actors['alex']['reused'])
        self.assertEqual(actors['alex']['dependency_hash'],before_alex['dependency_hash'])
        self.assertEqual(actors['dana']['candidates'][0]['text'], 'Dana asks Alex for a clear answer.')
        self.assertEqual(to_text(store), self.text)

    def test_http_form_port_loads_replacement_and_detects_changed_file(self):
        data_dir = self.root / 'character_data'
        data_dir.mkdir()
        def package(name, response):
            value = {'dataset_id':name, 'revision':'1', 'schema_id':'narrative.behavior.v1',
                     'owner_id':'dana', 'review_status':'pending_review',
                     'rules':[{'rule_id':'respond','event':'challenge','response':response,'state':'alert'}]}
            raw = json.dumps(value).encode('utf-8')
            (data_dir / (name + '.json')).write_bytes(raw)
            return {'dataset_id':name,'revision':'1','schema_id':'narrative.behavior.v1',
                    'domain':'behavior_rules','relative_path':name + '.json',
                    'content_hash':hashlib.sha256(raw).hexdigest()}
        root_ref = package('base', 'Dana takes a measured breath.')
        form_ref = package('alert', 'Dana calls for help.')
        initial = self.start_http(); text, rev = initial['text'], initial['revision']
        status, root = self.post('/api/node', {'text':text,'revision':rev,'id':'port:dana.port.data'})
        root['data']['bindings'] = [root_ref]
        status, updated = self.post('/api/node/update', {'text':text,'revision':rev,
            'id':'port:dana.port.data','value':json.dumps(root['data'])})
        self.assertEqual(status, 200, updated); rev = updated['revision']
        status, project = self.post('/api/project', {'text':text,'revision':rev,'event':'challenge'})
        actors = {r['entity']:r for r in project['reactions']}
        self.assertEqual(actors['dana']['data_input']['status'], 'resolved')
        self.assertEqual(actors['dana']['candidates'][0]['text'], 'Dana takes a measured breath.')
        self.assertEqual(actors['dana']['data_input']['mode'], 'inherit')
        alex_key = actors['alex']['dependency_hash']
        status, port = self.post('/api/node', {'text':text,'revision':rev,'id':'port:dana.state.alert.port.data'})
        port['data'].update(mode='replace',bindings=[form_ref])
        status, updated = self.post('/api/node/update', {'text':text,'revision':rev,
            'id':'port:dana.state.alert.port.data','value':json.dumps(port['data'])})
        self.assertEqual(status, 200, updated); rev = updated['revision']
        status, project = self.post('/api/project', {'text':text,'revision':rev,'event':'challenge'})
        actors = {r['entity']:r for r in project['reactions']}
        self.assertEqual(actors['dana']['candidates'][0]['text'], 'Dana calls for help.')
        self.assertEqual(actors['alex']['dependency_hash'], alex_key)
        self.assertTrue(actors['alex']['reused'])
        status, graph = self.post('/api/graph', {'text':text,'revision':rev,'entity':'dana'})
        self.assertEqual(status, 200, graph)
        self.assertIn('dana.state.alert.port.data', graph['html'])
        self.assertIn('Characters &amp; forms', graph['html'])
        status, saved = self.post('/api/save', {'text':text,'revision':rev})
        self.assertEqual(status, 200, saved)
        with urlopen(self.url+'/api/source?reload=1') as response: reloaded = json.load(response)
        status, project = self.post('/api/project', {'text':text,'revision':reloaded['revision'],'event':'challenge'})
        dana = next(r for r in project['reactions'] if r['entity']=='dana')
        self.assertEqual(dana['candidates'][0]['text'], 'Dana calls for help.')
        (data_dir/'alert.json').write_text('{}',encoding='utf-8')
        status, project = self.post('/api/project', {'text':text,'revision':reloaded['revision'],'event':'challenge'})
        dana = next(r for r in project['reactions'] if r['entity']=='dana')
        self.assertEqual(dana['data_input']['status'],'unresolved')
        self.assertEqual(dana['candidates'],[])
        self.assertFalse(dana['reused'])

    def test_port_cannot_escape_project_or_be_embedded_in_actor(self):
        from narrative_composer.graph.data_ports import DatasetRef, load_bound_data
        store = self.store()
        data = copy.deepcopy(store.node('ent:dana').data)
        data['data_port'] = {'id':'dana.port.data'}
        with self.assertRaises(ValueError): apply_node_edit(store,'ent:dana',json.dumps(data))
        actor = self.registry['dana']
        actor.data_port.bindings = [DatasetRef(
            dataset_id='outside',revision='1',schema_id='narrative.behavior.v1',domain='behavior_rules',
            content_hash='0'*64,relative_path='../outside.json')]
        result, records = load_bound_data(actor,None,self.root/'character_data')
        self.assertEqual(result['status'],'unresolved')
        self.assertIn('inside',result['reason'])
        self.assertEqual(records,[])

    def test_bound_form_data_reaches_the_composer_prompt(self):
        from narrative_composer.graph.data_ports import DatasetRef
        from narrative_composer.workspace import compose_beat
        data_dir = self.root/'character_data'
        data_dir.mkdir()
        package = {'dataset_id':'alert','revision':'2','schema_id':'narrative.behavior.v1',
                   'owner_id':'dana', 'review_status':'pending_review',
                   'rules':[{'rule_id':'ask','event':'observe','response':'Dana asks Alex for help.'}]}
        raw = json.dumps(package).encode('utf-8')
        (data_dir/'alert.json').write_bytes(raw)
        port = self.registry['dana'].states[1].data_port
        port.mode = 'replace'
        port.bindings = [DatasetRef(dataset_id='alert',revision='2',schema_id='narrative.behavior.v1',
            domain='behavior_rules',relative_path='alert.json',content_hash=hashlib.sha256(raw).hexdigest())]
        class CapturingProvider:
            def generate_rewrite(self, request, prompt):
                self.prompt = prompt
                return 'Dana waits by the cold table.'
        provider = CapturingProvider()
        pending = compose_beat(self.store(),provider)
        self.assertIn('Dana asks Alex for help.',provider.prompt)
        self.assertEqual(pending['decision'],'pending review')
        (data_dir/'alert.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Character data is unresolved'):
            compose_beat(self.store(),provider)

    def test_requested_forms_have_independent_ports_on_one_character_path(self):
        registry = load_registry()
        stella = registry['stella']
        by_slug = {state.slug:state for state in stella.states}
        for slug in ('standard','nerd_20','nerd_40','nerd_70','nerd_80','big_tiddy_steve'):
            self.assertEqual(by_slug[slug].data_port.id, 'stella.state.'+slug+'.port.data')
        self.assertEqual(stella.data_port.id,'stella.port.data')
        rainee = registry['rainee']
        self.assertTrue({'strip_tease','madonna','christie_brinkley','heather_locklear',
                         'kim_basinger','debbie_harry','bo_derek','peter'} <= {s.slug for s in rainee.states})
        self.assertEqual(len({s.data_port.id for s in rainee.states}),len(rainee.states))

    def test_story_form_markers_are_observations_not_automatic_transitions(self):
        from narrative_composer.graph.extract import extract_run
        from narrative_composer.parser.fountain_lexer import FountainParser
        graph = StoryGraph.from_registry(load_registry())
        text = ('INT. ROOM - DAY\n\nStella waits.\n\n> **NERD SATURATION — 40%**\n'
                '\nINT. ROOM - CONTINUOUS\n\n> **NERD SATURATION — 120%**\n')
        run = extract_run(FountainParser.parse(text),graph,'hot_scoomp_main','test')
        marker = next(o for o in run.observations if o['kind']=='state_marker')
        self.assertEqual(marker['state'],'nerd_40')
        self.assertFalse(marker['accepted'])
        self.assertTrue(any(o['kind']=='state_marker' and o['state']=='big_tiddy_steve'
                            for o in run.observations))
        self.assertEqual(run.xforms,[])

    def test_hypothetical_form_recomputation_does_not_change_story(self):
        store = self.store()
        before = copy.deepcopy(store.meta['run_graph'])
        result = project_report(store,'challenge',state_overrides={'dana':'dana.state.base'})
        dana = next(r for r in result['reactions'] if r['entity']=='dana')
        self.assertEqual(dana['state_id'],'dana.state.base')
        self.assertEqual(dana['state_source'],'hypothetical')
        self.assertEqual(store.meta['run_graph'],before)
        with self.assertRaises(ValueError):
            project_report(store,'challenge',state_overrides={'dana':'alex.state.base'})

    def test_discovered_character_requires_review_and_gets_an_empty_port(self):
        initial = self.start_http()
        text = initial['text'] + '\nMORGAN\nHello there.\n'
        status, candidates = self.post('/api/cast/candidates', {'text':text, 'revision':initial['revision']})
        self.assertEqual(status, 200, candidates)
        candidate = next(item for item in candidates['candidates'] if item['entity_id']=='morgan')
        self.assertTrue(candidate['evidence']['block_id'])
        status, _ = self.post('/api/cast/add', {'text':text, 'revision':candidates['revision'],
                                                 'entity_id':'morgan', 'reviewed':False})
        self.assertEqual(status, 400)
        status, added = self.post('/api/cast/add', {'text':text, 'revision':candidates['revision'],
                                                     'entity_id':'morgan', 'reviewed':True})
        self.assertEqual(status, 200, added)
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)
        self.assertFalse((self.root/'characters/morgan.json').exists())
        self.assertIn('port:morgan.port.data', self.server.store.nodes)
        status, inspected = self.post('/api/data/inspect', {'text':text, 'revision':added['revision'],
                                                          'id':'port:morgan.port.data'})
        self.assertEqual(inspected['data_input']['status'], 'unbound')
        status, saved = self.post('/api/save', {'text':text, 'revision':inspected['revision']})
        self.assertEqual(status, 200, saved)
        with urlopen(self.url+'/api/source?reload=1') as response:
            reloaded = json.load(response)
        status, nodes = self.post('/api/nodes', {'text':reloaded['text'], 'revision':reloaded['revision']})
        self.assertTrue(any(node['id']=='ent:morgan' for node in nodes['nodes']))
        self.assertEqual(self.source.read_text(encoding='utf-8'), text)

    def test_empty_form_replacement_does_not_inherit_embedded_actor_rules(self):
        alert = next(state for state in self.registry['dana'].states if state.slug == 'alert')
        alert.data_port.mode = 'replace'
        alert.data_port.bindings = []
        replaced = project_report(self.store(), 'challenge', state_overrides={'dana': alert.id})
        result = next(item for item in replaced['reactions'] if item['entity'] == 'dana')
        self.assertEqual(result['data_input']['status'], 'unbound')
        self.assertEqual(result['candidates'], [])
        alert.data_port.mode = 'inherit'
        inherited = project_report(self.store(), 'challenge', state_overrides={'dana': alert.id})
        result = next(item for item in inherited['reactions'] if item['entity'] == 'dana')
        self.assertEqual(result['candidates'][0]['rule_id'], 'check_latch')

    def test_section_initial_form_is_scoped_and_does_not_invent_a_transition(self):
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        manifest['initial_character_states'] = {'dana':'dana.state.alert'}
        manifest['initial_state_provenance'] = {'status':'author review pending'}
        store = self.store('INT. HALL - DAY\n\n**DANA-ALERT:** "Hello."\n', manifest=manifest)
        self.assertEqual(store.meta['run_graph']['state_instances'][0]['source'],'initial')
        self.assertEqual(store.meta['run_graph']['state_instances'][0]['state_id'],'dana.state.alert')
        self.assertFalse(store.meta['run_graph']['transform_instances'])
        self.assertFalse(any(d['rule_id']=='G2_CUE_STATE_MISMATCH' for d in store.meta['diagnostics']))
        self.assertEqual(project_report(store)['stages']['analysis'],'pending review')
        manifest['initial_character_states'] = {'dana':'alex.state.base'}
        with self.assertRaises(ValueError): self.store(manifest=manifest)

    def test_http_reviewed_form_survives_save_and_detects_stale_evidence(self):
        self.text = self.text.replace('> EVENT: pulse','').replace(
            'Dana changes into the alert form. The lamp clicks against the cold table.','')
        self.source.write_text(self.text,encoding='utf-8')
        initial = self.start_http(); text, revision = initial['text'], initial['revision']
        status, nodes = self.post('/api/nodes',{'text':text,'revision':revision})
        obs = next(o for o in nodes['observations'] if o['kind']=='cue_assertion' and not o['accepted'])
        status, rejected = self.post('/api/observation/accept',{'text':text,'revision':revision,**obs,'reviewed':False})
        self.assertEqual(status,400)
        status, accepted = self.post('/api/observation/accept',{'text':text,'revision':revision,**obs,'reviewed':True})
        self.assertEqual(status,200,accepted); revision=accepted['revision']
        self.assertTrue(any(s['source']=='reviewed' and s['state_id']=='dana.state.alert'
                            for s in self.server.store.meta['run_graph']['state_instances']))
        self.assertFalse(self.server.store.meta['run_graph']['transform_instances'])
        self.assertTrue(any(d['rule_id']=='G9_REVIEWED_STATE_CAUSE_PENDING'
                            for d in self.server.store.meta['diagnostics']))
        with urlopen(self.url+'/api/source') as response: self.assertTrue(json.load(response)['dirty'])
        status, saved = self.post('/api/save',{'text':text,'revision':revision})
        self.assertEqual(status,200,saved)
        with urlopen(self.url+'/api/source?reload=1') as response: reloaded=json.load(response)
        self.assertTrue(self.server.store.meta['manifest_payload']['reviewed_state_observations'])
        changed=text.replace('**DANA-ALERT:**','**DANA-ALERT (CONT\'D):**')
        status, result = self.post('/api/nodes',{'text':changed,'revision':reloaded['revision']})
        self.assertEqual(status,200,result)
        self.assertTrue(any(d['rule_id']=='G10_STALE_STATE_REVIEW' for d in result['diagnostics']))

    def test_review_question_is_not_presented_as_technical_failure_but_gate_remains(self):
        text = self.text.replace('> EVENT: pulse', '')
        store = self.store(text)
        raw = next(d for d in store.meta['diagnostics'] if d['rule_id']=='G2_CUE_STATE_MISMATCH')
        self.assertEqual(raw['severity'], 'ERROR')
        report = project_report(store)
        displayed = next(d for d in report['diagnostics'] if d['rule_id']=='G2_CUE_STATE_MISMATCH')
        self.assertEqual(displayed['severity'], 'WARNING')
        self.assertEqual(displayed['classification'], 'author_review_question')
        self.assertEqual(displayed['gate_severity'], 'ERROR')
        self.assertEqual(report['stages']['analysis'], 'pending review')

    def test_composer_uses_source_trace_without_behavior_profile(self):
        from narrative_composer.workspace import compose_beat
        actor = self.registry['dana']
        actor.attributes.pop('behavior_rules', None)
        actor.attributes.pop('personality_profile', None)
        actor.data_port.bindings = []
        for state in actor.states:
            state.data_port.mode = 'inherit'
            state.data_port.bindings = []
        class CaptureProvider:
            def generate_rewrite(self, request, prompt):
                self.prompt = prompt
                return 'Dana waits by the cold table.'
        provider = CaptureProvider()
        proposal = compose_beat(self.store(), provider)
        self.assertIn('Bounded source-writing samples', provider.prompt)
        self.assertIn('Dana changes into the alert form', provider.prompt)
        self.assertTrue(proposal['authored_evidence'])
        self.assertTrue(all('excerpt' not in item for item in proposal['authored_evidence']))
        self.assertEqual(proposal['decision'], 'pending review')

    def test_composer_reports_preexisting_graph_errors_without_hiding_them(self):
        from narrative_composer.workspace import compose_beat
        text = self.text.replace('> EVENT: pulse','').replace(
            'Dana changes into the alert form. The lamp clicks against the cold table.','')
        store = self.store(text)
        self.assertTrue(any(d['rule_id']=='G2_CUE_STATE_MISMATCH' for d in store.meta['diagnostics']))
        proposal = compose_beat(store,Provider('Dana waits by the cold table.'))
        self.assertGreater(proposal['preexisting_graph_errors'],0)
        self.assertEqual(proposal['graph_validation'],'no new errors')
        self.assertEqual(to_text(store),text)

    def test_cue_and_discovery_cannot_create_legality(self):
        store = self.store(self.text.replace('> EVENT: pulse', '').replace(
            'Dana changes into the alert form. The lamp clicks against the cold table.', ''))
        self.assertFalse(store.meta['run_graph']['transform_instances'])
        self.assertTrue(any(d['rule_id']=='G2_CUE_STATE_MISMATCH' for d in store.meta['diagnostics']))
        net = build_network_for_text('**DANA-DRAGON:**\nHello.\n','recovery','review')
        run, report, graph, discoveries = cook_network_to_report(net,'recovery','review',{'graph':StoryGraph.from_registry(self.registry)})
        self.assertTrue(discoveries.new_states)
        self.assertNotIn('dragon', {s.slug for s in graph.entities['dana'].states})
        self.assertFalse(run['transform_instances'])

    def test_graph_context_change_invalidates_cooked_result(self):
        graph = StoryGraph.from_registry(self.registry)
        net = build_network_for_text(self.text,'recovery','review')
        first = cook_network_to_report(net,'recovery','review',{'graph':graph})[1]
        graph.entities['dana'].transforms = []
        second = cook_network_to_report(net,'recovery','review',{'graph':graph})[1]
        self.assertEqual(first['summary']['errors'],0)
        self.assertGreater(second['summary']['review_questions'],0)
        self.assertGreater(second['summary']['gate_errors'],0)

    def test_pattern_detected_unverified_form_is_not_asserted_as_illegal_transition(self):
        graph = StoryGraph.from_registry(self.registry)
        graph.entities['dana'].transforms = []
        net = build_network_for_text(self.text, 'recovery', 'review')
        run, report, _, _ = cook_network_to_report(net, 'recovery', 'review', {'graph':graph})
        self.assertTrue(any(v['rule_id']=='G8_UNVERIFIED_EVENT' and v['requires_author_review']
                            for v in report['violations']))
        self.assertFalse(any(v['rule_id']=='G1_ILLEGAL_TRANSITION' for v in report['violations']))
        self.assertTrue(any(x['source']=='unverified_observation' for x in run['transform_instances']))
        self.assertGreater(report['summary']['gate_errors'], 0)

    def test_sidecar_revision_is_a_cache_dependency(self):
        clear_build_cache()
        original = build_store(self.source,self.manifest,registry=self.registry,canon='recovery')
        entries = entries_from_document(parse_document(self.text))
        entries[0]['id'] = 'author-title-id'
        save_entries(sidecar_path(self.source),entries)
        updated = build_store(self.source,self.manifest,registry=self.registry,canon='recovery')
        self.assertNotIn('blk:author-title-id',original.nodes)
        self.assertIn('blk:author-title-id',updated.nodes)

    def test_valid_but_partial_sidecar_conflicts_without_reassigning_ids(self):
        from narrative_composer.compiler.identity import IdentitySidecarError
        entries = entries_from_document(parse_document(self.text))
        ids_path = sidecar_path(self.source)
        save_entries(ids_path, entries[:-1])
        before_story, before_ids = self.source.read_bytes(), ids_path.read_bytes()
        with self.assertRaises(IdentitySidecarError):
            self.store()
        self.assertEqual(self.source.read_bytes(), before_story)
        self.assertEqual(ids_path.read_bytes(), before_ids)
        save_entries(ids_path, entries)
        self.source.write_text(self.text.replace('Dana locks the door.', 'Dana opens the door.'),encoding='utf-8')
        with self.assertRaises(IdentitySidecarError):
            build_store(self.source,self.manifest,registry=self.registry,canon='recovery',use_cache=False)
        clear_build_cache()
        build_store(self.source,self.manifest,registry=self.registry,canon='recovery',
                    allow_unverified_identity_reconciliation=True)
        with self.assertRaises(IdentitySidecarError):
            build_store(self.source,self.manifest,registry=self.registry,canon='recovery')

    def test_semantic_reversal_rejected_and_valid_change_needs_decision(self):
        text = 'Dana locks the door. Alex stays inside with the key.'
        bad = plan_conditioning(text,Provider('Dana opens the door. Alex leaves with the key.'))
        self.assertFalse(bad[0].accepted)
        good = plan_conditioning(text,Provider())
        self.assertTrue(good[0].accepted)
        self.assertEqual(apply_proposals(text,good),(text,0))
        updated,count = apply_proposals(text,good,[good[0].block_id])
        self.assertEqual(count,1)
        self.assertIn('Dana locks the door.',updated)
        with self.assertRaises(ValueError): apply_proposals(text+' Changed.',good,[good[0].block_id])

    def test_world_constraints_reach_conditioner_and_review_escapes_html(self):
        m = json.loads(self.manifest.read_text())
        m['props']['lamp']['lifecycle'] = 'destroyed'
        provider = Provider('Dana turns on the lamp. Alex stays at the table.')
        proposals = plan_conditioning('Dana waits at the table. Alex stays at the table.',provider,manifest=m)
        self.assertEqual(provider.request.active_props['lamp'],'destroyed')
        self.assertFalse(proposals[0].accepted)
        proposals[0].proposed = '<img src=x onerror="alert(1)">'
        self.assertNotIn('<img',_review_html('<title>',proposals))

    def test_failed_validation_preserves_every_authored_file(self):
        store = self.store()
        store.node('ent:dana').data['base_state'] = 'missing'
        store.meta['dirty_entities'] = ['dana']
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValueError):
            save_workspace(store,self.text+'New text.',self.source,entity_dir=self.root/'characters',
                           nodes_out=None,manifest_path=self.manifest)
        self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def test_external_edit_conflicts_instead_of_overwriting(self):
        store = self.store()
        self.source.write_text(self.text+'External edit.',encoding='utf-8')
        with self.assertRaises(WorkspaceConflict):
            save_workspace(store,self.text,self.source,nodes_out=None,manifest_path=self.manifest)
        self.assertIn('External edit.',self.source.read_text(encoding='utf-8'))

    def test_external_edit_immediately_after_save_is_not_adopted_as_our_baseline(self):
        store = self.store()
        actual_commit = commit_files
        def commit_then_external_edit(*args, **kwargs):
            actual_commit(*args, **kwargs)
            self.source.write_text('External edit after our commit.\n', encoding='utf-8')
        with patch('narrative_composer.editor.commit_files', side_effect=commit_then_external_edit):
            save_workspace(store,self.text,self.source,entity_dir=self.root/'characters',
                           nodes_out=None,manifest_path=self.manifest)
        with self.assertRaises(WorkspaceConflict):
            save_workspace(store,self.text,self.source,entity_dir=self.root/'characters',
                           nodes_out=None,manifest_path=self.manifest)
        self.assertEqual(self.source.read_text(encoding='utf-8'), 'External edit after our commit.\n')

    def test_generated_outputs_refuse_existing_files_and_source_aliases(self):
        from narrative_composer.compiler.convergence_harness import ClosedLoopConvergenceHarness
        from narrative_composer.compiler.html_compiler import compile_screenplay_html
        from narrative_composer.graph.pipeline import process_text
        existing = self.root/'reader.html'
        existing.write_bytes(b'author output')
        original = self.source.read_bytes()
        with self.assertRaises(FileExistsError):
            compile_screenplay_html(self.source, existing)
        harness = ClosedLoopConvergenceHarness(manifest_path=str(self.manifest), provider_mode='mock', max_iterations=1)
        with self.assertRaises(FileExistsError):
            harness.run(self.source, html_out_path=self.source, in_place=False)
        with self.assertRaises(FileExistsError):
            harness.run(self.source, html_out_path=existing, in_place=False)
        graph_folder = self.root/'graph_out'
        graph_folder.mkdir()
        sentinel = graph_folder/'run.report.json'
        sentinel.write_bytes(b'prior report')
        with self.assertRaises(FileExistsError):
            process_text('INT. HALL - DAY\n', 'recovery', 'run', graph_folder, learn=False)
        with self.assertRaises(ValueError):
            process_text('INT. HALL - DAY\n', 'recovery', '../escape', graph_folder, learn=False)
        self.assertEqual(existing.read_bytes(), b'author output')
        self.assertEqual(sentinel.read_bytes(), b'prior report')
        self.assertEqual(self.source.read_bytes(), original)

    def test_interrupted_multi_file_write_rolls_back(self):
        a,b = self.root/'a.txt',self.root/'b.txt'
        a.write_bytes(b'old-a');b.write_bytes(b'old-b')
        original_replace = Path.replace
        failed = []
        def replace(path,target):
            if Path(target)==b and not failed:
                failed.append(True)
                raise OSError('simulated disk failure')
            return original_replace(path,target)
        with patch.object(Path,'replace',replace):
            with self.assertRaises(OSError):
                commit_files({a:b'new-a',b:b'new-b'},{str(a):file_hash(a),str(b):file_hash(b)},self.root/'journal')
        self.assertEqual(a.read_bytes(),b'old-a');self.assertEqual(b.read_bytes(),b'old-b')

    def test_disposable_copy_never_replays_original_absolute_journal(self):
        outside = Path(self.temp.name) / 'authored.md'
        outside.write_bytes(b'current author work')
        journal_dir = self.root / 'story.md.revisions' / 'prepared'
        journal_dir.mkdir(parents=True)
        (journal_dir / '0.before').write_bytes(b'older work')
        journal = {'status': 'prepared', 'files': [{'path': str(outside), 'backup': '0.before',
            'before': hashlib.sha256(b'older work').hexdigest(),
            'after': hashlib.sha256(b'current author work').hexdigest()}]}
        (journal_dir / 'journal.json').write_text(json.dumps(journal), encoding='utf-8')
        (self.root / 'story.md.rich.json').write_text('{}', encoding='utf-8')
        copy = Path(self.temp.name) / 'sandbox'
        shutil.copytree(self.root, copy, ignore=ignore_recovery_artifacts)
        self.assertFalse((copy / 'story.md.revisions').exists())
        self.assertTrue((copy / 'story.md.rich.json').exists())
        recover_transactions(copy / 'story.md.revisions')
        self.assertEqual(outside.read_bytes(), b'current author work')

    def start_http(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),EditorHandler)
        server.screenplay_path=self.source;server.manifest_path=self.manifest
        server.entity_dir=self.root/'characters';server.store=None;server.store_text=None;server.canon='recovery'
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        self.url='http://127.0.0.1:'+str(server.server_port)
        self.server=server
        with urlopen(self.url+'/api/source') as response: return json.load(response)

    def post(self,route,payload):
        request=Request(self.url+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(request) as response:return response.status,json.load(response)
        except HTTPError as exc:return exc.code,json.load(exc)

    def test_http_corrupt_identity_sidecar_refuses_reload_without_writing(self):
        self.start_http()
        source_before = self.source.read_bytes()
        identity = sidecar_path(self.source)
        identity.write_bytes(b'{broken identity')
        with self.assertRaises(HTTPError) as failure:
            urlopen(self.url + '/api/source?reload=1')
        self.assertEqual(failure.exception.code, 409)
        self.assertIn('Identity sidecar', json.load(failure.exception)['error'])
        self.assertEqual(identity.read_bytes(), b'{broken identity')
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_form_appearances_link_to_current_edition_blocks(self):
        initial = self.start_http()
        status, result = self.post('/api/state/appearances', {'text':initial['text'],
            'revision':initial['revision'], 'id':'st:dana.state.alert'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['state_id'], 'dana.state.alert')
        self.assertTrue(result['appearances'])
        self.assertTrue(any(item['block_ids'] for item in result['appearances']))
        for item in result['appearances']:
            for block_id in item['block_ids']:
                self.assertEqual(self.server.store.node(block_id).data['line'], item['line'])
        self.assertIn('does not approve', result['notice'])
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_character_trace_links_authored_dialogue_and_candidate_actions_without_profile(self):
        initial = self.start_http()
        status, result = self.post('/api/character/trace', {'text':initial['text'],
            'revision':initial['revision'], 'id':'ent:dana'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['edition'], self.source.name)
        self.assertEqual(Path(result['edition_path']), self.source.resolve())
        self.assertTrue(any(e['kind']=='cue_attributed_dialogue' and 'lamp' in e['text'] for e in result['entries']))
        actions = [e for e in result['entries'] if e['kind']=='lexical_action_mention']
        self.assertTrue(any('locks the door' in e['text'] for e in actions))
        self.assertTrue(all('require review' in e['status'] for e in actions))
        self.assertTrue(all(self.server.store.node(e['block_id']).data['line']==e['line'] for e in result['entries']))
        self.assertIn('not approved behavior', result['notice'])

    def test_author_can_add_form_port_and_save_without_inventing_an_event(self):
        initial = self.start_http()
        source_before = self.source.read_bytes()
        status, created = self.post('/api/state/create', {'text':initial['text'], 'revision':initial['revision'],
            'entity_id':'dana', 'slug':'halfway', 'label':'Halfway', 'reviewed':True})
        self.assertEqual(status, 200, created)
        self.assertEqual(created['state_id'], 'dana.state.halfway')
        self.assertEqual(created['port_id'], 'dana.state.halfway.port.data')
        self.assertIn('st:dana.state.halfway', self.server.store.nodes)
        self.assertIn('port:dana.state.halfway.port.data', self.server.store.nodes)
        self.assertFalse(any(o.get('state') == 'halfway' for o in self.server.store.meta['run_graph']['observations']))
        status, linked = self.post('/api/transform/create', {'text':initial['text'], 'revision':created['revision'],
            'entity_id':'dana', 'from_state':'dana.state.base', 'to_state':'dana.state.halfway', 'reviewed':True})
        self.assertEqual(status, 200, linked)
        self.assertEqual(linked['transform_id'], 'dana.xform.base__halfway')
        self.assertTrue(self.server.store.node('xf:dana.xform.base__halfway').data['attributes']['provisional'])
        self.assertFalse(any(item.get('to_state') == 'dana.state.halfway'
                             for item in self.server.store.meta['run_graph']['transform_instances']))
        status, duplicated = self.post('/api/state/create', {'text':initial['text'], 'revision':linked['revision'],
            'entity_id':'dana', 'slug':'halfway', 'label':'Duplicate', 'reviewed':True})
        self.assertEqual(status, 409, duplicated)
        status, invalid = self.post('/api/transform/create', {'text':initial['text'], 'revision':linked['revision'],
            'entity_id':'dana', 'from_state':'dana.state.base', 'to_state':'alex.state.base', 'reviewed':True})
        self.assertEqual(status, 400, invalid)
        status, saved = self.post('/api/save', {'text':initial['text'], 'revision':linked['revision']})
        self.assertEqual(status, 200, saved)
        with urlopen(self.url+'/api/source?reload=1') as response:
            reloaded = json.load(response)
        status, trace = self.post('/api/character/trace', {'text':reloaded['text'],
            'revision':reloaded['revision'], 'id':'ent:dana'})
        self.assertEqual(status, 200, trace)
        state = next(item for item in trace['states'] if item['id']=='dana.state.halfway')
        self.assertEqual(state['availability'], 'available; no detected appearance')
        self.assertIn('xf:dana.xform.base__halfway', self.server.store.nodes)
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_condition_target_resolves_only_single_action_line(self):
        initial = self.start_http()
        request = {'text':initial['text'], 'revision':initial['revision']}
        status, target = self.post('/api/condition/target', {**request, 'line':7})
        self.assertEqual(status, 200, target)
        self.assertTrue(target['block_id'])
        status, failure = self.post('/api/condition/target', {**request, 'line':9})
        self.assertEqual(status, 400, failure)
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_condition_proposal_keeps_revision_and_candidate_graph_links(self):
        initial = self.start_http()
        node = next(n for n in self.server.store.of_kind('block')
                    if n.data.get('role') == 'action' and 'Dana locks the door' in n.data['text'])
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()):
            status, result = self.post('/api/condition', {'text':initial['text'], 'revision':initial['revision'],
                'provider':'mock', 'limit':1, 'target_block_ids':[node.id.removeprefix('blk:')]})
        self.assertEqual(status, 200, result)
        proposal = result['patches'][0]
        self.assertEqual(proposal['base_revision'], initial['revision'])
        context = proposal['graph_context']
        self.assertEqual(context['edition'], self.source.name)
        self.assertEqual(context['target_block_id'], node.id)
        self.assertEqual({x['entity'] for x in context['character_links']}, {'dana', 'alex'})
        self.assertTrue(all('require review' in x['status'] for x in context['character_links']))
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_outline_note_trace_is_labeled_without_claiming_an_event(self):
        self.text = '# An outline\n\n> Dana might visit Alex.\n'
        self.source.write_text(self.text, encoding='utf-8')
        initial = self.start_http()
        payload = {'text':initial['text'], 'revision':initial['revision']}
        status, trace = self.post('/api/character/trace', {**payload, 'id':'ent:dana'})
        self.assertEqual(status, 200, trace)
        note = next(item for item in trace['entries'] if item['kind']=='lexical_note_mention')
        self.assertIn('not an established event or dialogue', note['status'])
        self.assertFalse(trace['observations'])
        status, report = self.post('/api/project', payload)
        self.assertEqual(status, 200, report)
        self.assertEqual(report['stages']['analysis'], 'not modeled')

    def test_deepseek_is_default_and_venice_can_be_selected_without_fallback(self):
        initial = self.start_http()
        with urlopen(self.url+'/') as response:
            page = response.read().decode('utf-8')
        self.assertIn('<option value="deepseek" selected>DeepSeek · primary</option>', page)
        self.assertIn('<option value="gemini_session">Gemini · session</option>', page)
        self.server.default_provider = 'venice'
        with urlopen(self.url+'/') as response:
            page = response.read().decode('utf-8')
        self.assertIn('<option value="venice" selected>Venice · backup</option>', page)
        self.server.default_provider = 'deepseek'
        with patch.object(EditorHandler, '_provider', return_value=Provider()) as selected:
            status, result = self.post('/api/condition', {'text':initial['text'], 'revision':initial['revision']})
        self.assertEqual(status, 200, result)
        selected.assert_called_once_with('deepseek')
        class UnavailableProvider:
            def generate_rewrite(self, request, prompt):
                raise RuntimeError('simulated outage')
        with patch.object(EditorHandler, '_provider', return_value=UnavailableProvider()) as selected:
            status, result = self.post('/api/condition', {'text':initial['text'], 'revision':initial['revision']})
        self.assertEqual(status, 200, result)
        selected.assert_called_once_with('deepseek')
        self.assertTrue(any('provider error' in p['reason'] for p in result['patches']))
        self.assertFalse(any(p['eligible'] for p in result['patches']))
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_gemini_session_reaches_editor_conditioner_without_api_fallback(self):
        class FakeGeminiSession:
            model = 'gemini-session-fixture'
            def __init__(self): self.calls=[]
            def run(self, prompt, context=None, label=None):
                self.calls.append((prompt, context, label))
                return 'Dana waits beside the quiet table.'
            def start_connect(self): pass
            def snapshot(self): return {'connected':True,'messages':[],'running':False,'error':'',
                                         'model':self.model,'connection_note':'fixture'}
        initial = self.start_http(); fake = FakeGeminiSession()
        with patch.object(EditorHandler, '_gemini_session', return_value=fake):
            status, result = self.post('/api/condition', {'text':initial['text'],
                'revision':initial['revision'], 'provider':'gemini_session', 'limit':1})
            self.assertEqual(status, 200, result)
            self.assertTrue(fake.calls)
            self.assertTrue(all(p['provider']=='gemini_session' for p in result['patches']))
            status, _ = self.post('/api/gemini/connect', {'text':initial['text'],'revision':result['revision']})
            self.assertEqual(status, 200)
            with urlopen(self.url+'/api/gemini/chat') as response:
                self.assertEqual(json.load(response)['model'], fake.model)
        self.assertEqual(self.source.read_text(encoding='utf-8'),self.text)

    def test_http_preview_edit_save_reload_export_same_identity(self):
        initial=self.start_http()
        text=initial['text'];rev=initial['revision']
        status,nodes=self.post('/api/nodes',{'text':text,'revision':rev})
        self.assertEqual(status,200)
        cue=next(n for n in self.server.store.of_kind('block') if n.data['role']=='cue')
        status,edited=self.post('/api/node/update',{'text':text,'revision':rev,'id':cue.id,'value':'ALEX'})
        self.assertEqual(status,200);self.assertIn('**ALEX:**',edited['text'])
        text,rev=edited['text'],edited['revision']
        status,preview=self.post('/api/render',{'text':text,'revision':rev})
        self.assertIn('data-block="'+cue.id[4:]+'"',preview['html'])
        status,saved=self.post('/api/save',{'text':text,'revision':rev})
        self.assertEqual(status,200,saved)
        self.assertEqual(self.source.read_text(encoding='utf-8'),text)
        status,export=self.post('/api/export',{'text':text,'revision':rev,'format':'source'})
        self.assertEqual(export['content'],text)
        with urlopen(self.url+'/api/source?reload=1') as response:reloaded=json.load(response)
        self.assertEqual(reloaded['text'],text)
        self.assertIn(cue.id,self.server.store.nodes)

    def test_http_browser_noop_preserves_crlf_bytes(self):
        raw=self.text.replace('\n','\r\n').encode('utf-8')
        self.source.write_bytes(raw)
        initial=self.start_http()
        status,rendered=self.post('/api/render',{'text':initial['text'].replace('\r\n','\n'),
            'revision':initial['revision'],'browser_text':True})
        self.assertEqual(status,200,rendered)
        with urlopen(self.url+'/api/source') as response: self.assertFalse(json.load(response)['dirty'])
        status,saved=self.post('/api/save',{'text':initial['text'].replace('\r\n','\n'),
            'revision':rendered['revision'],'browser_text':True})
        self.assertEqual(status,200,saved)
        self.assertEqual(self.source.read_bytes(),raw)

    def test_timeline_switch_keeps_unsaved_draft_and_scopes_manifest(self):
        other=self.root/'other.md'; other.write_text('INT. OTHER - DAY\n\nAlex waits.\n',encoding='utf-8')
        other_manifest=self.root/'other.manifest.json'; shutil.copy2(self.manifest,other_manifest)
        timeline=self.root/'timeline.json'
        timeline.write_text(json.dumps({'sections':[
            {'id':'first','story':'story.md','manifest':'manifest.json','canon':'recovery'},
            {'id':'second','story':'other.md','manifest':'other.manifest.json','canon':'recovery'}]}),encoding='utf-8')
        initial=self.start_http();self.server.timeline_path=timeline
        with urlopen(self.url+'/api/timeline') as response: listing=json.load(response)
        self.assertEqual(listing['current'],'first')
        status,result=self.post('/api/timeline/open',{'text':initial['text']+'unsaved',
            'revision':initial['revision'],'id':'second'})
        self.assertEqual(status,409,result)
        self.assertEqual(self.server.screenplay_path,self.source)
        self.assertEqual(self.server.store.meta['revision'],initial['revision'])
        status,result=self.post('/api/timeline/open',{'text':initial['text'],
            'revision':initial['revision'],'id':'second'})
        self.assertEqual(status,200,result)
        with urlopen(self.url+'/api/source') as response: loaded=json.load(response)
        self.assertEqual(loaded['text'],other.read_bytes().decode('utf-8'))
        self.assertEqual(self.server.manifest_path,other_manifest.resolve())
        self.assertEqual(self.source.read_text(encoding='utf-8'),self.text)

    def test_http_stale_revision_rejected_and_manifest_diagnostics_fresh(self):
        initial=self.start_http();text=initial['text'];rev=initial['revision']
        prop=copy.deepcopy(self.server.store.node('prop:lamp').data);prop['lifecycle']='destroyed'
        status,edit=self.post('/api/node/update',{'text':text,'revision':rev,'id':'prop:lamp','value':json.dumps(prop)})
        self.assertEqual(status,200)
        status,result=self.post('/api/save',{'text':text,'revision':rev})
        self.assertEqual(status,409)
        candidate=text+'\nDana knocks over the lamp.\n'
        status,result=self.post('/api/nodes',{'text':candidate,'revision':edit['revision']})
        self.assertEqual(status,200,result)
        self.assertTrue(any(d['rule_id']=='RULE_2A_ZOMBIE_PROP_DESTRUCTION' for d in result['diagnostics']))

    def test_composer_missing_precondition_and_pending_review_never_commit(self):
        from narrative_composer.models.causal_dag import CausalDAG,StoryBeatNode
        from narrative_composer.store import _manifest_models
        from narrative_composer.compiler.composer_engine import NarrativeComposerEngine,PendingBeatReview
        m=json.loads(self.manifest.read_text());ep,sp=_manifest_models(m)
        beat=StoryBeatNode.model_validate(m['beats']['observe']);dag=CausalDAG(beats={'observe':beat})
        engine=NarrativeComposerEngine(dag,ep,sp,llm_generate_fn=lambda _: 'Dana waits.',character_nodes={})
        with self.assertRaises(PendingBeatReview):engine.process_beat(beat)
        self.assertFalse(beat.is_completed);self.assertEqual(engine.committed_script_buffer,[])
        beat.required_prop_states[0]['required_lifecycle']='destroyed'
        with self.assertRaises(ValueError):engine.process_beat(beat)
        beat.prerequisite_beat_ids=['missing']
        with self.assertRaises(ValueError):dag.get_next_actionable_beat()

    def test_source_provenance_cannot_be_replaced_by_model_window(self):
        from narrative_composer.ingest.validator import ExtractionValidator
        from narrative_composer.ingest.schemas import SceneObservation
        obs=SceneObservation(scene_id='invented',source_id='invented',window_start=100,window_end=200,
            characters=[{'character_id':'alex','idiolect':[{'category':'idiolect','trait':'Speaks calmly.',
                         'evidence_start':150,'evidence_end':151}]}])
        result=ExtractionValidator().validate(obs,{'start':0,'end':10,'scene_id':'actual','source_id':'actual'})
        self.assertFalse(result.is_valid)

    def test_http_generated_beat_stays_pending_until_review_and_survives_reload(self):
        initial=self.start_http()
        with patch('narrative_composer.prose.providers.create_prose_provider',return_value=Provider('Dana waits by the cold table.')):
            status,planned=self.post('/api/compose',{'text':initial['text'],'revision':initial['revision'],'provider':'mock'})
        self.assertEqual(status,200,planned)
        proposal=planned['patches'][0]
        self.assertFalse(json.loads(self.manifest.read_text())['beats']['observe'].get('is_completed',False))
        self.assertEqual(self.source.read_text(encoding='utf-8'),self.text)
        status,applied=self.post('/api/proposal/apply',{'text':initial['text'],'revision':planned['revision'],
                            'proposal_id':proposal['proposal_id'],'reviewed':True})
        self.assertEqual(status,200,applied)
        self.assertIn('Dana waits by the cold table.',applied['text'])
        self.assertTrue(self.server.store.meta['manifest_payload']['beats']['observe']['is_completed'])
        status,saved=self.post('/api/save',{'text':applied['text'],'revision':applied['revision']})
        self.assertEqual(status,200,saved)
        self.assertTrue(json.loads(self.manifest.read_text())['beats']['observe']['is_completed'])
        with urlopen(self.url+'/api/source?reload=1') as response: reloaded=json.load(response)
        status,project=self.post('/api/project',{'text':reloaded['text'],'revision':reloaded['revision']})
        self.assertEqual(project['decision_history_status'],'loaded')
        self.assertEqual(project['decisions'][-1]['decision'],'accepted by author')
        self.assertTrue((self.root/'story.md.nodes.json').exists())

    def test_conditioner_proposal_requires_explicit_review_through_http(self):
        initial=self.start_http()
        with patch('narrative_composer.prose.providers.create_prose_provider',return_value=Provider()):
            status,planned=self.post('/api/condition',{'text':initial['text'],'revision':initial['revision'],'provider':'mock'})
        self.assertEqual(status,200,planned)
        proposal=next(p for p in planned['patches'] if p['eligible'])
        status,rejected=self.post('/api/proposal/apply',{'text':initial['text'],'revision':planned['revision'],
                            'proposal_id':proposal['proposal_id'],'reviewed':False})
        self.assertEqual(status,400)
        status,applied=self.post('/api/proposal/apply',{'text':initial['text'],'revision':planned['revision'],
                            'proposal_id':proposal['proposal_id'],'reviewed':True})
        self.assertEqual(status,200,applied)
        self.assertIn('A cold draft moves past.',applied['text'])

    def test_old_conditioner_proposal_is_revalidated_before_application(self):
        from narrative_composer.proposal_store import ProposalStore
        self.text = 'INT. ROOM - DAY\n\n第二行：大家一起检查计划。安全校对。\n'
        self.source.write_text(self.text,encoding='utf-8')
        initial = self.start_http(); text, revision = initial['text'], initial['revision']
        block = next(n for n in self.server.store.of_kind('block') if '大家' in n.data['text'])
        change = {'proposal_id':'old','base_revision':revision,
            'edition_path':str(self.source.resolve()), 'block_id':block.id[4:],
            'rule_id':'PROSE_CONDITIONING', 'original':block.data['text'],
            'proposed':'检查计划。安全校对。','eligible':True}
        ProposalStore(self.source).append([change])
        status, history = self.post('/api/proposals', {'text':text,'revision':revision})
        self.assertFalse(history['patches'][0]['eligible'])
        self.assertIn('dropped group subject',history['patches'][0]['reason'])
        status, result = self.post('/api/proposal/apply', {'text':text,'revision':revision,
            'proposal_id':'old','reviewed':True})
        self.assertEqual(status,400,result)
        self.assertIn('dropped group subject',result['error'])
        self.assertEqual(to_text(self.server.store),text)

    def test_proposal_remains_visible_and_can_be_retried_when_history_write_fails(self):
        initial = self.start_http()
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()), \
             patch('narrative_composer.proposal_store.ProposalStore.append', side_effect=OSError('full disk')):
            status, planned = self.post('/api/condition', {'text':initial['text'],
                'revision':initial['revision'], 'provider':'mock'})
        self.assertEqual(status, 200, planned)
        proposal = next(p for p in planned['patches'] if p['eligible'])
        self.assertTrue(proposal['history_unavailable'])
        self.assertIn('A cold draft', proposal['proposed'])
        status, history = self.post('/api/proposals', {'text':initial['text'], 'revision':planned['revision']})
        self.assertTrue(any(p['proposal_id'] == proposal['proposal_id'] for p in history['patches']))
        status, result = self.post('/api/proposal/apply', {'text':initial['text'], 'revision':history['revision'],
            'proposal_id':proposal['proposal_id'], 'reviewed':True})
        self.assertEqual(status, 409, result)
        status, result = self.post('/api/proposal/recover', {'text':initial['text'], 'revision':history['revision'],
            'proposal_id':proposal['proposal_id']})
        self.assertEqual(status, 200, result)
        status, history = self.post('/api/proposals', {'text':initial['text'], 'revision':result['revision']})
        saved = next(p for p in history['patches'] if p['proposal_id'] == proposal['proposal_id'])
        self.assertFalse(saved.get('history_unavailable', False))
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_failed_request_history_recovers_batch_and_replays_after_restart(self):
        initial = self.start_http()
        payload = {'text':initial['text'], 'revision':initial['revision'], 'provider':'mock',
                   'limit':2, 'request_id':'d'*32}
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()), \
             patch('narrative_composer.proposal_store.ProposalStore.finish_request', side_effect=OSError('disk full')):
            status, planned = self.post('/api/condition', payload)
        self.assertEqual(status, 200, planned)
        self.assertTrue(planned['patches'])
        self.assertTrue(all(p['history_unavailable'] for p in planned['patches']))
        status, saved = self.post('/api/proposal/recover', {'text':initial['text'], 'revision':initial['revision'],
            'proposal_id':planned['patches'][0]['proposal_id']})
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['saved_count'], len(planned['patches']))
        self.server.shutdown(); self.server.server_close(); self.start_http()
        with patch('narrative_composer.prose.providers.create_prose_provider', side_effect=AssertionError('called again')):
            status, replay = self.post('/api/condition', payload)
        self.assertEqual(status, 200, replay)
        self.assertEqual([p['proposal_id'] for p in replay['patches']], [p['proposal_id'] for p in planned['patches']])
        self.assertTrue(all(not p.get('history_unavailable') for p in replay['patches']))
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_copied_history_is_visible_but_cannot_apply_to_another_edition(self):
        from narrative_composer.proposal_store import ProposalStore
        initial = self.start_http()
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()):
            status, planned = self.post('/api/condition', {'text':initial['text'],
                'revision':initial['revision'], 'provider':'mock'})
        proposal = next(p for p in planned['patches'] if p['eligible'])
        other = self.root/'other.md'
        other.write_bytes(self.source.read_bytes())
        shutil.copy2(ProposalStore(self.source).path, ProposalStore(other).path)
        self.server.screenplay_path, self.server.store, self.server.store_text = other, None, None
        with urlopen(self.url+'/api/source') as response:
            reopened = json.load(response)
        self.assertEqual(reopened['revision'], initial['revision'])
        status, history = self.post('/api/proposals', {'text':reopened['text'], 'revision':reopened['revision']})
        copied = next(p for p in history['patches'] if p['proposal_id'] == proposal['proposal_id'])
        self.assertTrue(copied['history_stale'])
        status, result = self.post('/api/proposal/apply', {'text':reopened['text'], 'revision':reopened['revision'],
            'proposal_id':proposal['proposal_id'], 'reviewed':True})
        self.assertEqual(status, 409, result)
        self.assertEqual(other.read_bytes(), self.source.read_bytes())

    def test_proposals_survive_replanning_timeline_switch_and_server_restart(self):
        other = self.root/'other.md'
        other.write_text('INT. OTHER - DAY\n\nAlex waits.\n', encoding='utf-8')
        other_manifest = self.root/'other.manifest.json'
        shutil.copy2(self.manifest, other_manifest)
        timeline = self.root/'timeline.json'
        timeline.write_text(json.dumps({'sections': [
            {'id':'first', 'story':'story.md', 'manifest':'manifest.json', 'canon':'recovery'},
            {'id':'second', 'story':'other.md', 'manifest':'other.manifest.json', 'canon':'recovery'}]}), encoding='utf-8')
        initial = self.start_http()
        self.server.timeline_path = timeline
        original = self.source.read_bytes()
        identifiers = []
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()):
            for _ in range(2):
                status, result = self.post('/api/condition', {'text': initial['text'],
                    'revision': initial['revision'], 'provider':'mock'})
                self.assertEqual(status, 200, result)
                identifiers.extend(item['proposal_id'] for item in result['patches'])
        self.assertGreaterEqual(len(identifiers), 2)
        self.assertEqual(len(set(identifiers)), len(identifiers))
        status, decision = self.post('/api/proposal/reject', {'text':initial['text'],
            'revision':initial['revision'], 'proposal_id':identifiers[0], 'reviewed':True})
        self.assertEqual(status, 200, decision)
        status, _ = self.post('/api/timeline/open', {'text':initial['text'], 'revision':initial['revision'], 'id':'second'})
        self.assertEqual(status, 200)
        with urlopen(self.url+'/api/source') as response:
            second = json.load(response)
        status, history = self.post('/api/proposals', {'text':second['text'], 'revision':second['revision']})
        self.assertEqual(history['patches'], [])
        status, _ = self.post('/api/timeline/open', {'text':second['text'], 'revision':second['revision'], 'id':'first'})
        self.assertEqual(status, 200)
        with urlopen(self.url+'/api/source') as response:
            first = json.load(response)
        status, history = self.post('/api/proposals', {'text':first['text'], 'revision':first['revision']})
        self.assertEqual({item['proposal_id'] for item in history['patches']}, set(identifiers))
        self.server.shutdown()
        self.server.server_close()
        reopened = self.start_http()
        status, history = self.post('/api/proposals', {'text':reopened['text'], 'revision':reopened['revision']})
        self.assertEqual({item['proposal_id'] for item in history['patches']}, set(identifiers))
        rejected = next(item for item in history['patches'] if item['proposal_id']==identifiers[0])
        self.assertEqual(rejected['author_decision'], 'rejected')
        status, _ = self.post('/api/proposal/apply', {'text':reopened['text'], 'revision':reopened['revision'],
            'proposal_id':identifiers[0], 'reviewed':True})
        self.assertEqual(status, 400)
        status, _ = self.post('/api/proposal/restore', {'text':reopened['text'], 'revision':reopened['revision'],
            'proposal_id':identifiers[0], 'reviewed':True})
        self.assertEqual(status, 200)
        status, history = self.post('/api/proposals', {'text':reopened['text']+'\nAn edit.', 'revision':reopened['revision']})
        self.assertTrue(all(item['history_stale'] for item in history['patches']))
        self.assertEqual(self.source.read_bytes(), original)

    def test_request_replay_after_restart_returns_same_proposals_without_provider_call(self):
        initial = self.start_http()
        payload = {'text':initial['text'], 'revision':initial['revision'], 'provider':'mock', 'limit':1,
                   'request_id':'a'*32}
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=Provider()):
            status, first = self.post('/api/condition', payload)
        self.assertEqual(status, 200, first)
        self.assertTrue(first['patches'])
        self.server.shutdown(); self.server.server_close()
        reopened = self.start_http()
        self.assertEqual(reopened['revision'], initial['revision'])
        with patch('narrative_composer.prose.providers.create_prose_provider', side_effect=AssertionError('provider called again')):
            status, replay = self.post('/api/condition', payload)
        self.assertEqual(status, 200, replay)
        self.assertEqual([p['proposal_id'] for p in first['patches']], [p['proposal_id'] for p in replay['patches']])
        status, history = self.post('/api/proposals', {'text':initial['text'], 'revision':initial['revision']})
        self.assertEqual(len(history['patches']), len(first['patches']))
        changed = dict(payload, limit=2)
        status, error = self.post('/api/condition', changed)
        self.assertEqual(status, 400)
        self.assertIn('different input', error['error'])

    def test_request_claim_is_shared_by_independent_store_instances(self):
        from narrative_composer.proposal_store import ProposalStore
        first, second = ProposalStore(self.source), ProposalStore(self.source)
        self.assertIsNone(first.claim_request('b'*32, 'fingerprint'))
        with self.assertRaisesRegex(ValueError, 'outcome is uncertain'):
            second.claim_request('b'*32, 'fingerprint')
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_failed_batch_commit_never_leaves_partial_proposals(self):
        import sqlite3
        from narrative_composer.proposal_store import ProposalStore
        history = ProposalStore(self.source)
        history.claim_request('e'*32, 'fingerprint')
        with self.assertRaises(sqlite3.IntegrityError):
            history.finish_request('e'*32, [{'proposal_id':'same'}, {'proposal_id':'same'}])
        self.assertEqual(history.list(), [])
        with self.assertRaisesRegex(ValueError, 'outcome is uncertain'):
            history.claim_request('e'*32, 'fingerprint')
        self.assertEqual(self.source.read_text(encoding='utf-8'), self.text)

    def test_duplicate_inflight_request_is_rejected_without_extra_provider_call(self):
        initial = self.start_http()
        entered, release = threading.Event(), threading.Event()
        outcomes, calls = {}, []
        class SlowProvider:
            def generate_rewrite(self, request, prompt):
                calls.append(1)
                entered.set()
                if not release.wait(10):
                    raise RuntimeError('provider barrier timed out')
                return request.original_text + ' A cold draft moves past.'
        payload = {'text':initial['text'], 'revision':initial['revision'], 'provider':'mock', 'limit':1}
        def first():
            outcomes['first'] = self.post('/api/condition', payload)
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=SlowProvider()):
            worker = threading.Thread(target=first, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(5))
            try:
                status, duplicate = self.post('/api/condition', payload)
                self.assertEqual(status, 409, duplicate)
                self.assertIn('already running', duplicate['error'])
            finally:
                release.set()
                worker.join(10)
        self.assertEqual(outcomes['first'][0], 200, outcomes['first'])
        self.assertEqual(len(calls), 1)
        status, history = self.post('/api/proposals', {'text':initial['text'], 'revision':initial['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(len(history['patches']), 1)

    def test_slow_provider_does_not_block_save_and_result_remains_stale_in_history(self):
        initial = self.start_http()
        entered, release, saved = threading.Event(), threading.Event(), threading.Event()
        outcomes = {}
        class SlowProvider:
            def generate_rewrite(self, request, prompt):
                entered.set()
                if not release.wait(15):
                    raise RuntimeError('provider barrier timed out')
                return request.original_text + ' A cold draft moves past.'
        def plan():
            outcomes['plan'] = self.post('/api/condition', {'text':initial['text'],
                'revision':initial['revision'], 'provider':'mock', 'limit':1})
        updated = initial['text'] + '\nA new author note.\n'
        def save():
            try:
                outcomes['save'] = self.post('/api/save', {'text':updated, 'revision':initial['revision']})
            finally:
                saved.set()
        with patch('narrative_composer.prose.providers.create_prose_provider', return_value=SlowProvider()):
            planning = threading.Thread(target=plan, daemon=True)
            planning.start()
            self.assertTrue(entered.wait(5))
            saving = threading.Thread(target=save, daemon=True)
            saving.start()
            saved_while_blocked = saved.wait(5)
            release.set()
            saving.join(10)
            planning.join(10)
        self.assertTrue(saved_while_blocked, 'save waited on the provider request')
        self.assertEqual(outcomes['save'][0], 200, outcomes['save'])
        self.assertEqual(outcomes['plan'][0], 200, outcomes['plan'])
        proposal = outcomes['plan'][1]['patches'][0]
        self.assertTrue(proposal['history_stale'])
        self.assertEqual(self.source.read_bytes(), updated.encode('utf-8'))
        status, history = self.post('/api/proposals', {'text':updated, 'revision':outcomes['save'][1]['revision']})
        saved_proposal = next(item for item in history['patches'] if item['proposal_id']==proposal['proposal_id'])
        self.assertTrue(saved_proposal['history_stale'])
        status, _ = self.post('/api/proposal/apply', {'text':updated, 'revision':history['revision'],
                                'proposal_id':proposal['proposal_id'], 'reviewed':True})
        self.assertEqual(status, 409)

    def test_accepted_proposal_cannot_introduce_unverified_form_transition(self):
        initial=self.start_http(); text,revision=initial['text'],initial['revision']
        block=next(n for n in self.server.store.of_kind('block')
                   if n.data['role']=='action' and 'Dana locks the door' in n.data['text'])
        self.server.pending_changes={'candidate':{'proposal_id':'candidate','base_revision':revision,
            'edition_path':str(self.source.resolve()),
            'block_id':block.id[4:],'original':block.data['text'],
            'proposed':'Dana changes into the alert form.','eligible':True}}
        status,result=self.post('/api/proposal/apply',{'text':text,'revision':revision,
            'proposal_id':'candidate','reviewed':True})
        self.assertEqual(status,400,result)
        self.assertIn('G8_UNVERIFIED_EVENT',result['error'])
        self.assertEqual(to_text(self.server.store),text)
        self.assertEqual(self.source.read_text(encoding='utf-8'),self.text)

    def test_unmodeled_coverage_and_chinese_quality_are_explicit(self):
        from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
        store=self.store(manifest={'facts':{},'props':{},'beats':{},'initial_beliefs':{}})
        self.assertEqual(project_report(store)['status'],'not modeled')
        report=ProseDiagnosticsAnalyzer.analyze('丹娜锁上门。亚历克斯留在里面。')
        self.assertTrue(any('Language coverage' in warning for warning in report.warnings))

    def test_new_story_intake_opens_as_a_project_and_never_overwrites_edits(self):
        from narrative_composer.story import run_story
        incoming=self.root/'incoming.md'
        incoming.write_text('INT. HALL - DAY\n\n**DANA**\nHello.\n',encoding='utf-8')
        output=self.root/'intake'
        report=run_story(incoming,output,canon='recovery',cast={'dana':{'display_name':'Dana'}})
        registry=load_registry(output/'characters')
        store=build_store(output/'story.md',output/'manifest.json',registry=registry,canon='recovery')
        self.assertIn('ent:dana',store.nodes)
        self.assertEqual(project_report(store)['status'],'not modeled')
        (output/'story.md').write_text('An authored edit.',encoding='utf-8')
        with self.assertRaises(FileExistsError):run_story(incoming,output)
        self.assertEqual((output/'story.md').read_text(encoding='utf-8'),'An authored edit.')

    def test_busy_proposal_does_not_consume_request_id(self):
        from narrative_composer.editor import guard_identical_provider_request, provider_work_without_commit_lock
        from narrative_composer.persistence import COMMIT_LOCK

        initial = self.start_http()
        pending = {"text": initial["text"], "revision": initial["revision"],
                   "provider": "deepseek", "request_id": "b" * 32, "limit": 1}
        active = {"text": initial["text"], "revision": initial["revision"], "provider": "codex"}
        with COMMIT_LOCK:
            with guard_identical_provider_request(
                self.server, "/api/compose", self.source.resolve(), active,
            ), provider_work_without_commit_lock():
                with patch("narrative_composer.prose.providers.create_prose_provider",
                           return_value=Provider()) as factory:
                    status, busy = self.post("/api/condition", pending)
                self.assertEqual(status, 409, busy)
                self.assertIn("Another provider proposal", busy["error"])
                factory.assert_not_called()

        with patch("narrative_composer.prose.providers.create_prose_provider",
                   return_value=Provider()) as factory:
            status, planned = self.post("/api/condition", pending)
        self.assertEqual(status, 200, planned)
        factory.assert_called_once_with("deepseek")
        with patch("narrative_composer.prose.providers.create_prose_provider",
                   side_effect=AssertionError("Completed request regenerated")):
            status, replay = self.post("/api/condition", pending)
        self.assertEqual(status, 200, replay)
        self.assertEqual(replay["patches"], planned["patches"])


if __name__=='__main__':unittest.main()
