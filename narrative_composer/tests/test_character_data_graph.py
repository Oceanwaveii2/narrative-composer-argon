import hashlib
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from narrative_composer.graph.data_ports import DatasetRef, load_bound_data
from narrative_composer.graph.registry import load_registry
from narrative_composer.store import build_store, document_from_store
from narrative_composer.workspace import compose_beat, evaluate_characters

FIXTURE = Path(__file__).parent / 'fixtures' / 'recovery_project'


class CharacterDataGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        shutil.copytree(FIXTURE, self.root)
        self.data = self.root / 'character_data'
        self.data.mkdir()
        self.registry = load_registry(self.root / 'characters')

    def package(self, name, domain, schema, **payload):
        record = {'dataset_id': name, 'revision': '1', 'schema_id': schema, **payload}
        raw = json.dumps(record).encode('utf-8')
        (self.data / (name + '.json')).write_bytes(raw)
        return DatasetRef(dataset_id=name, revision='1', schema_id=schema, domain=domain,
                          relative_path=name + '.json', content_hash=hashlib.sha256(raw).hexdigest())

    def profile(self, name, drive):
        return self.package(name, 'personality_profile', 'narrative.dialectic.v1', owner_id='dana',
            review_status='pending_review', profile={'character_id':'dana','display_name':'Dana',
            'thesis':{'pole_name':'A','core_drive':drive},
            'antithesis':{'pole_name':'B','core_drive':'seek help'}})

    def store(self, text=None):
        return build_store(self.root/'story.md', self.root/'manifest.json', registry=self.registry,
                           canon='recovery', text=text, use_cache=False)

    def test_source_index_profile_override_and_composer_share_the_same_port_data(self):
        original = (self.root/'story.md').read_bytes()
        block = document_from_store(self.store()).blocks[0]
        evidence = self.package('evidence', 'story_evidence', 'narrative.story-index.v1', owner_id='dana',
            sources=[{'section':'first','file':'story.md','sha256':hashlib.sha256(original).hexdigest(),
                      'references':[{'block_id':block.id,'line':block.line,
                                     'line_sha256':hashlib.sha256(block.raw.encode('utf-8')).hexdigest()}]}])
        base, alternate = self.profile('base', 'protect the record'), self.profile('alert', 'ask a question')
        actor = self.registry['dana']
        actor.data_port.bindings = [evidence, base]
        alert = next(s for s in actor.states if s.slug == 'alert')
        alert.data_port.mode = 'override'
        alert.data_port.bindings = [alternate]
        info, records = load_bound_data(actor, alert.id, self.data)
        self.assertEqual(info['status'], 'resolved')
        self.assertEqual({r['dataset_id'] for r in records}, {'evidence', 'alert'})
        store = self.store()
        self.assertEqual(len(store.outgoing('port:dana.port.data', 'binds_dataset')), 2)
        self.assertEqual(len(store.outgoing('port:dana.state.alert.port.data', 'binds_dataset')), 1)
        results = evaluate_characters(store, 'observe', state_overrides={'dana':alert.id})
        dana = next(r for r in results if r['entity'] == 'dana')
        self.assertEqual(dana['source_evidence']['status'], 'current')
        self.assertEqual(dana['profiles'][0]['dataset_id'], 'alert')
        class Provider:
            def generate_rewrite(self, request, prompt):
                self.prompt = prompt
                return 'Dana waits by the cold table.'
        provider = Provider()
        result = compose_beat(store, provider, state_overrides={'dana':alert.id})
        self.assertIn('ask a question', provider.prompt)
        self.assertIn('Unreviewed character-profile material', provider.prompt)
        self.assertIn('dana.state.alert', provider.prompt)
        self.assertIn('DANA-ALERT', provider.prompt)
        self.assertIn('drafting assumption, not an approved transition', provider.prompt)
        self.assertEqual(result['decision'], 'pending review')
        self.assertEqual(result['state_overrides'], {'dana':alert.id})
        base_result = compose_beat(store, provider, state_overrides={'dana':'dana.state.base'})
        self.assertIn('protect the record', provider.prompt)
        self.assertEqual(base_result['state_overrides'], {'dana':'dana.state.base'})
        with self.assertRaisesRegex(ValueError, 'active in the selected beat'):
            compose_beat(store, provider, state_overrides={'missing':'missing.state.base'})
        changed = self.store(text=original.decode('utf-8') + '\nNew sentence.\n')
        stale = next(r for r in evaluate_characters(changed, 'observe') if r['entity']=='dana')
        self.assertEqual(stale['source_evidence']['status'], 'stale')
        self.assertEqual(stale['source_evidence']['references'], 0)

    def test_profile_for_another_character_fails_closed(self):
        ref = self.package('wrong', 'personality_profile', 'narrative.dialectic.v1', owner_id='dana',
            review_status='pending_review', profile={'character_id':'someone_else','display_name':'X',
            'thesis':{'pole_name':'A','core_drive':'A'},'antithesis':{'pole_name':'B','core_drive':'B'}})
        self.registry['dana'].data_port.bindings = [ref]
        info, records = load_bound_data(self.registry['dana'], None, self.data)
        self.assertEqual(info['status'], 'unresolved')
        self.assertEqual(records, [])
        self.assertIn('identity', info['reason'].lower())

    def test_legacy_root_domains_conflict_with_extend_and_override_is_explicit(self):
        actor = self.registry['dana']
        actor.attributes['personality_profile'] = {
            'character_id':'dana', 'display_name':'Dana',
            'thesis':{'pole_name':'A', 'core_drive':'root drive'},
            'antithesis':{'pole_name':'B', 'core_drive':'seek help'}}
        alert = next(state for state in actor.states if state.slug == 'alert')
        behavior = self.package('form_rules', 'behavior_rules', 'narrative.behavior.v1',
                                owner_id='dana', review_status='pending_review',
                                rules=[{'rule_id':'form','event':'challenge','response':'form response'}])
        profile = self.profile('form_profile', 'form drive')
        for ref in (behavior, profile):
            alert.data_port.mode = 'extend'
            alert.data_port.bindings = [ref]
            info, _ = load_bound_data(actor, alert.id, self.data)
            self.assertEqual(info['status'], 'conflict')
            reaction = next(r for r in evaluate_characters(self.store(), 'challenge',
                            state_overrides={'dana':alert.id}) if r['entity'] == 'dana')
            self.assertEqual(reaction['data_input']['status'], 'conflict')
            self.assertEqual(reaction['candidates'], [])
            with self.assertRaisesRegex(ValueError, 'unresolved or conflicting'):
                compose_beat(self.store(), state_overrides={'dana':alert.id})
            alert.data_port.mode = 'override'
            info, _ = load_bound_data(actor, alert.id, self.data)
            self.assertEqual(info['status'], 'resolved')
            self.assertNotIn(ref.domain, info['embedded_domains'])
        alert.data_port.mode = 'replace'
        alert.data_port.bindings = []
        info, _ = load_bound_data(actor, alert.id, self.data)
        self.assertEqual(info['status'], 'unbound')
        self.assertEqual(info['embedded_domains'], [])

    def test_behavior_package_requires_matching_owner_and_review(self):
        actor = self.registry['dana']
        for owner, review in [('alex', 'approved'), (None, 'approved'), ('dana', None)]:
            actor.data_port.bindings = [self.package('owner_check', 'behavior_rules', 'narrative.behavior.v1',
                owner_id=owner, review_status=review, rules=[])]
            info, records = load_bound_data(actor, None, self.data)
            self.assertEqual(info['status'], 'unresolved')
            self.assertEqual(records, [])
            self.assertIn('owner or review', info['reason'])

    def test_source_references_and_cache_are_document_scoped_and_isolated(self):
        original = (self.root/'story.md').read_bytes()
        block = document_from_store(self.store()).blocks[0]
        ref = {'block_id':block.id, 'line':block.line,
               'line_sha256':hashlib.sha256(block.raw.encode('utf-8')).hexdigest()}
        evidence = self.package('evidence_cache', 'story_evidence', 'narrative.story-index.v1', owner_id='dana',
            sources=[{'section':'first', 'file':'story.md', 'sha256':hashlib.sha256(original).hexdigest(),
                      'references':[ref]}])
        self.registry['dana'].data_port.bindings = [evidence]
        cache = {}
        first = next(r for r in evaluate_characters(self.store(), 'challenge', cache) if r['entity']=='dana')
        self.assertEqual(first['source_evidence']['status'], 'current')
        first['source_evidence']['edition'] = 'mutated by caller'
        again = next(r for r in evaluate_characters(self.store(), 'challenge', cache) if r['entity']=='dana')
        self.assertTrue(again['reused'])
        self.assertEqual(again['source_evidence']['edition'], 'first')
        bad = dict(ref, block_id='does-not-exist', line=999, line_sha256='0'*64)
        evidence = self.package('broken_index', 'story_evidence', 'narrative.story-index.v1', owner_id='dana',
            sources=[{'section':'wrong', 'file':'story.md', 'sha256':hashlib.sha256(original).hexdigest(),
                      'references':[bad]}])
        self.registry['dana'].data_port.bindings = [evidence]
        broken = next(r for r in evaluate_characters(self.store(), 'challenge', cache) if r['entity']=='dana')
        self.assertEqual(broken['source_evidence']['status'], 'invalid references')
        self.assertEqual(broken['source_evidence']['references'], 0)

    def test_equal_text_in_another_edition_does_not_reuse_source_attribution(self):
        original = (self.root/'story.md').read_bytes()
        (self.root/'second.md').write_bytes(original)
        block = document_from_store(self.store()).blocks[0]
        ref = {'block_id':block.id, 'line':block.line,
               'line_sha256':hashlib.sha256(block.raw.encode('utf-8')).hexdigest()}
        evidence = self.package('two_editions', 'story_evidence', 'narrative.story-index.v1', owner_id='dana',
            sources=[{'section':section, 'file':filename, 'sha256':hashlib.sha256(original).hexdigest(),
                      'references':[ref]} for section, filename in [('first','story.md'),('second','second.md')]])
        self.registry['dana'].data_port.bindings = [evidence]
        cache = {}
        first = next(r for r in evaluate_characters(self.store(), 'challenge', cache) if r['entity']=='dana')
        second_store = build_store(self.root/'second.md', self.root/'manifest.json', registry=self.registry,
                                   canon='recovery', use_cache=False)
        second = next(r for r in evaluate_characters(second_store, 'challenge', cache) if r['entity']=='dana')
        self.assertEqual(first['source_evidence']['edition'], 'first')
        self.assertFalse(second['reused'])
        self.assertEqual(second['source_evidence']['edition'], 'second')

    def test_graph_viewer_distinguishes_current_stale_and_unchecked_source_links(self):
        from narrative_composer.graph.graph import StoryGraph
        from narrative_composer.graph.viewer import render_viewer
        original = (self.root/'story.md').read_bytes()
        block = document_from_store(self.store()).blocks[0]
        ref = {'block_id':block.id, 'line':block.line,
               'line_sha256':hashlib.sha256(block.raw.encode('utf-8')).hexdigest()}
        self.registry['dana'].data_port.bindings = [self.package('viewer_index', 'story_evidence',
            'narrative.story-index.v1', owner_id='dana', sources=[{'section':'first','file':'story.md',
            'sha256':hashlib.sha256(original).hexdigest(),'references':[ref]}])]
        graph = StoryGraph.from_registry(self.registry)
        for label, store, expected in [('current',self.store(),'current'),
                ('stale',self.store(text=original.decode('utf-8')+'\nChanged.\n'),'stale'),
                ('unchecked',None,'not checked')]:
            source_store = store or self.store()
            path = self.root/(label+'.html')
            render_viewer(source_store.meta['run_graph'], {}, path, graph=graph,
                          data_root=self.data, source_store=store)
            html = path.read_text(encoding='utf-8')
            self.assertIn('"source_evidence"',html)
            self.assertIn('"status": "'+expected+'"',html)

    def test_composer_binds_one_snapshot_and_rejects_changed_package_at_acceptance(self):
        from narrative_composer.persistence import WorkspaceConflict
        actor = self.registry['dana']
        alert = next(state for state in actor.states if state.slug == 'alert')
        alert.data_port.mode = 'replace'
        alert.data_port.bindings = [self.package('stable', 'behavior_rules', 'narrative.behavior.v1',
            owner_id='dana', review_status='pending_review',
            rules=[{'rule_id':'snapshot','event':'observe','response':'Dana pauses.'}])]
        class ChangingProvider:
            def generate_rewrite(provider, request, prompt):
                provider.prompt = prompt
                (self.data/'stable.json').write_text('{}', encoding='utf-8')
                return 'Dana waits by the cold table.'
        store = self.store()
        provider = ChangingProvider()
        candidate = compose_beat(store, provider, state_overrides={'dana':alert.id})
        self.assertIn('Dana pauses.', provider.prompt)
        with self.assertRaisesRegex(WorkspaceConflict, 'dependencies changed'):
            compose_beat(store, reviewed_text=candidate['proposed'], beat_id=candidate['beat_id'],
                         state_overrides={'dana':alert.id}, expected_data_dependencies=candidate['data_dependencies'])

    def test_annotation_for_missing_actor_fails_graph_validation(self):
        from narrative_composer.graph.graph import StoryGraph
        from narrative_composer.graph.models import Annotation
        graph = StoryGraph.from_registry(self.registry)
        graph.annotations['ann.missing.1'] = Annotation(id='ann.missing.1', target_id='missing',
                                                        source='fixture', kind='note', text='neutral')
        self.assertTrue(any('nonexistent' in error for error in graph.validate()))

    def test_form_replacement_also_stops_embedded_profile_reaching_composer(self):
        self.registry['dana'].attributes['personality_profile'] = {
            'character_id':'dana', 'display_name':'Dana',
            'thesis':{'pole_name':'A', 'core_drive':'protect the record'},
            'antithesis':{'pole_name':'B', 'core_drive':'seek help'}}
        alert = next(state for state in self.registry['dana'].states if state.slug == 'alert')
        alert.data_port.mode = 'replace'
        class Provider:
            def generate_rewrite(self, request, prompt):
                self.prompt = prompt
                return 'Dana waits by the cold table.'
        provider = Provider()
        compose_beat(self.store(), provider, state_overrides={'dana':alert.id})
        self.assertNotIn('protect the record', provider.prompt)
        alert.data_port.mode = 'inherit'
        compose_beat(self.store(), provider, state_overrides={'dana':alert.id})
        self.assertIn('protect the record', provider.prompt)

    def test_hypothetical_form_is_reviewable_without_authorizing_a_transition(self):
        from narrative_composer.store import to_text
        text = 'INT. HALL - DAY\n\nDana waits beside Alex.\n'
        store = self.store(text=text)
        class Provider:
            def generate_rewrite(self, request, prompt):
                return 'DANA-ALERT\nWe should check the latch.'
        candidate = compose_beat(store, Provider(), state_overrides={'dana':'dana.state.alert'})
        self.assertFalse(candidate['eligible'])
        self.assertEqual(candidate['state_assumptions'][0]['accepted'], 'dana.state.base')
        self.assertIn('DANA-ALERT', candidate['proposed'])
        self.assertEqual(to_text(store), text)
        with self.assertRaisesRegex(ValueError, 'review the form and transition'):
            compose_beat(store, reviewed_text=candidate['proposed'], state_overrides={'dana':'dana.state.alert'})

    def test_legacy_profile_strings_preserve_text_and_unknown_provenance(self):
        from narrative_composer.models.character import parse_compatible_profile
        raw = {'character_id':'dana','display_name':'Dana',
               'thesis':{'pole_name':'A','core_drive':'A'},
               'antithesis':{'pole_name':'B','core_drive':'B'},
               'kinematics':['moves carefully'],
               'synthesis_rules':[{'rule_id':'s1','trigger':'a question','mechanism':'asks for context'}]}
        before = copy.deepcopy(raw)
        profile = parse_compatible_profile(raw)
        self.assertEqual(raw, before)
        self.assertEqual(profile.kinematics[0].description, 'moves carefully')
        self.assertIsNone(profile.kinematics[0].confidence_score)
        self.assertIsNone(profile.kinematics[0].recurrence_count)
        self.assertEqual(profile.kinematics[0].provenance, [])
        self.assertIsNone(profile.synthesis_rules[0].example_volley)

    def test_rainee_collapse_does_not_enter_legacy_grouped_form(self):
        from narrative_composer.graph.extract import extract_run
        from narrative_composer.graph.graph import StoryGraph
        from narrative_composer.parser.fountain_lexer import FountainParser
        registry = load_registry()
        graph = StoryGraph.from_registry(registry)
        source = 'INT. ROOM - DAY\n\nRainee waits.\n\nRainee watches the shimmer fold as all six collapse like cards into a deck.\n'
        run = extract_run(FountainParser.parse(source), graph, 'hot_scoomp_main', 'check')
        self.assertFalse(any(o.get('kind') == 'state_event' and o.get('entity') == 'rainee'
                             and o.get('state') == 'strip_tease' for o in run.observations))
        entering = 'INT. ROOM - DAY\n\nRainee begins a strip tease.\n'
        run = extract_run(FountainParser.parse(entering), graph, 'hot_scoomp_main', 'check')
        self.assertTrue(any(o.get('kind') == 'state_event' and o.get('entity') == 'rainee'
                            and o.get('state') == 'strip_tease' for o in run.observations))


if __name__ == '__main__':
    unittest.main()
