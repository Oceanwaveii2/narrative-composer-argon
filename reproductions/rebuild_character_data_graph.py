"""Build a separate, source-linked character-data workspace from existing material."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_composer.editor import timeline_sections
from narrative_composer.graph.data_ports import load_bound_data
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.registry import load_registry
from narrative_composer.models.character import parse_compatible_profile
from narrative_composer.persistence import ignore_recovery_artifacts
from narrative_composer.store import build_store, document_from_store, registry_from_store, to_text
from narrative_composer.workspace import project_report


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_package(folder, name, package, domain):
    path = folder / (name + '.json')
    if path.exists():
        raise ValueError('Refusing to replace existing data package: ' + name)
    raw = (json.dumps(package, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    path.write_bytes(raw)
    return {'dataset_id': package['dataset_id'], 'revision': package['revision'],
            'content_hash': sha(raw), 'domain': domain, 'schema_id': package['schema_id'],
            'relative_path': path.name}


def patterns(actor):
    names = {actor.entity_id, actor.display_name, *actor.aliases}
    for state in actor.states:
        names.update(cue.cue for cue in state.cue_aliases)
    names = {name.strip() for name in names if isinstance(name, str) and len(name.strip()) >= 3}
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r')(?!\w)', re.I)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profiles', type=Path, required=True)
    args = parser.parse_args()
    source, target, profiles = args.workspace.resolve(), args.out.resolve(), args.profiles.resolve()
    if target.exists() or target.is_relative_to(source):
        raise ValueError('Choose a new workspace outside the source workspace')
    source_sections = timeline_sections(source / 'timeline.json')
    paths = {source / 'timeline.json', *(s['story'] for s in source_sections),
             *(s['manifest'] for s in source_sections), *(source / 'characters').rglob('*.json')}
    for name in ('hayley.json', 'rainee.json'):
        if (profiles / name).is_file():
            paths.add(profiles / name)
    proof = source / 'SOURCE_PROVENANCE.json'
    if proof.exists():
        paths.add(Path(json.loads(proof.read_text(encoding='utf-8'))['original_story_path']))
    before = {str(path): sha(path.read_bytes()) for path in paths}
    shutil.copytree(source, target, ignore=ignore_recovery_artifacts)
    sections = timeline_sections(target / 'timeline.json')
    # These legacy phrases describe leaving the grouped form, not entering it.
    # Preserve the prior workspace and change only the fresh candidate definition.
    rainee_path = target / 'characters' / 'rainee.json'
    if rainee_path.is_file():
        rainee = json.loads(rainee_path.read_text(encoding='utf-8'))
        for state in rainee.get('states', []):
            if state.get('slug') == 'strip_tease':
                state['enter_patterns'] = [p for p in state.get('enter_patterns', [])
                    if p not in (r'shimmer\s+folds?', r'all\s+six\s+collapse', r'cards\s+into\s+a\s+deck')]
        rainee_path.write_text(json.dumps(rainee, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    registry = load_registry(target / 'characters')
    checks = StoryGraph.from_registry(registry).validate()
    if checks:
        raise ValueError('Character definitions are invalid: ' + '; '.join(checks))
    matchers = {key: patterns(actor) for key, actor in registry.items()}
    indexes = {key: [] for key in registry}
    for section in sections:
        text = section['story'].read_bytes().decode('utf-8')
        store = build_store(section['story'], section['manifest'], registry=registry,
                            canon=section['canon'], text=text, use_cache=False)
        if to_text(store) != text:
            raise ValueError('Source projection changed: ' + section['id'])
        blocks = document_from_store(store).blocks
        for key, matcher in matchers.items():
            refs = []
            for block in blocks:
                match = matcher.search(block.raw)
                if match:
                    refs.append({'block_id': block.id, 'line': block.line, 'role': block.role.value,
                                 'match': match.group(0), 'line_sha256': sha(block.raw.encode('utf-8')),
                                 'status': 'candidate_mention'})
            indexes[key].append({'section': section['id'], 'file': section['story'].name,
                                 'canon': section['canon'], 'sha256': sha(text.encode('utf-8')),
                                 'references': refs})
        print('Indexed', section['id'], 'blocks:', len(blocks), flush=True)
    data_dir = target / 'character_data'
    data_dir.mkdir(exist_ok=True)
    package_report = {}
    for key, actor in registry.items():
        actor_path = target / 'characters' / (key + '.json')
        if not actor_path.is_file():
            raise ValueError('Character must have a named definition file: ' + key)
        raw = json.loads(actor_path.read_text(encoding='utf-8'))
        port = raw.setdefault('data_port', {'id': key + '.port.data', 'mode': 'inherit', 'bindings': []})
        bindings = port.setdefault('bindings', [])
        if any(b.get('domain') in ('story_evidence', 'personality_profile') for b in bindings):
            raise ValueError('Existing authored binding requires manual reconciliation: ' + key)
        evidence = {'dataset_id': key + '_source_index', 'revision': '1',
                    'schema_id': 'narrative.story-index.v1', 'owner_id': key,
                    'review_status': 'pending_review', 'method': 'lexical mentions; attribution requires review',
                    'sources': indexes[key]}
        bindings.append(save_package(data_dir, evidence['dataset_id'], evidence, 'story_evidence'))
        profile_file = profiles / ({'haley':'hayley', 'rainee':'rainee'}.get(key, '') + '.json')
        if profile_file.is_file():
            original_bytes = profile_file.read_bytes()
            profile = json.loads(original_bytes)
            parse_compatible_profile(profile)
            package = {'dataset_id': key + '_legacy_dialectic', 'revision': '1',
                       'schema_id': 'narrative.dialectic.v1', 'owner_id': key,
                       'review_status': 'pending_review', 'profile': profile,
                       'provenance': {'source_file': profile_file.name, 'sha256': sha(original_bytes),
                                      'identity_mapping': profile['character_id'] + ' -> ' + key}}
            bindings.append(save_package(data_dir, package['dataset_id'], package, 'personality_profile'))
        actor_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        package_report[key] = {'source_references': sum(len(s['references']) for s in indexes[key]),
                               'datasets': [b['domain'] for b in bindings]}
    rebuilt = load_registry(target / 'characters')
    errors = StoryGraph.from_registry(rebuilt).validate()
    if errors:
        raise ValueError('Rebuilt graph definitions invalid: ' + '; '.join(errors))
    sections_report = []
    for section in sections:
        store = build_store(section['story'], section['manifest'], registry=rebuilt,
                            canon=section['canon'], use_cache=False)
        if to_text(store).encode('utf-8') != section['story'].read_bytes():
            raise ValueError('Rebuilt graph changed source: ' + section['id'])
        report = project_report(store)
        for actor in registry_from_store(store).values():
            info, _ = load_bound_data(actor, None, data_dir)
            if info['status'] != 'resolved':
                raise ValueError('Unresolved root data: ' + actor.entity_id + ': ' + info['reason'])
        sections_report.append({'id': section['id'], 'nodes': len(store.nodes),
            'dataset_nodes': len(store.of_kind('dataset')),
            'graph_errors': sum(d['severity'] == 'ERROR' for d in report['diagnostics']),
            'source_sha256': sha(section['story'].read_bytes()),
            'reactions': [{'entity': r['entity'], 'data_status': r['data_input']['status'],
                'reaction_status': r['status'], 'source_evidence': r['source_evidence'],
                'profiles': r['profiles']} for r in report['reactions']]})
    after = {str(path): sha(path.read_bytes()) for path in paths}
    summary = {'source_workspace': str(source), 'rebuilt_workspace': str(target),
               'inputs_unchanged': before == after, 'input_hash_count': len(before),
               'graph_structure_errors': errors, 'characters': package_report, 'sections': sections_report,
               'corrections': ['Removed three exit/collapse phrases from Rainee grouped-form entry detection; no causal transition was approved.'],
               'caveats': ['Mention indexes require author review and are scoped to each edition.',
                           'Legacy profiles are pending review; source indexes are not personality models.',
                           'No new transition causes or behavior rules were fabricated.']}
    (target / 'CHARACTER_GRAPH_REBUILD_REPORT.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    if before != after:
        raise ValueError('An original input changed during the build')
    print('Rebuilt', len(rebuilt), 'actors in', len(sections), 'editions; inputs unchanged:', before == after, flush=True)


if __name__ == '__main__':
    main()
