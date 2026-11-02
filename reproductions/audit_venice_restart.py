"""Live Venice checks in disposable copies, with no proposal applied to a source."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reproductions.audit_timeline_pipeline import Session, inspect_case, snapshot


ROOT = Path(__file__).resolve().parents[1]


def neutral_composer(folder):
    fixture = ROOT / 'narrative_composer/tests/fixtures/recovery_project'
    project = folder / 'neutral_project'
    shutil.copytree(fixture, project)
    story, manifest = project / 'story.md', project / 'manifest.json'
    before = story.read_bytes()
    data_dir = project / 'character_data'
    data_dir.mkdir()
    package = {'dataset_id': 'alert_profile', 'revision': '1',
        'schema_id': 'narrative.dialectic.v1', 'owner_id': 'dana',
        'review_status': 'pending_review',
        'profile': {'character_id': 'dana', 'display_name': 'Dana',
            'thesis': {'pole_name': 'A', 'core_drive': 'protect the record'},
            'antithesis': {'pole_name': 'B', 'core_drive': 'ask for help'}}}
    raw = json.dumps(package).encode('utf-8')
    (data_dir / 'alert_profile.json').write_bytes(raw)
    binding = {'dataset_id': 'alert_profile', 'revision': '1',
        'schema_id': 'narrative.dialectic.v1', 'domain': 'personality_profile',
        'relative_path': 'alert_profile.json', 'content_hash': hashlib.sha256(raw).hexdigest()}
    actor_file = project / 'characters/dana.json'
    actor = json.loads(actor_file.read_text(encoding='utf-8'))
    state = next(s for s in actor['states'] if s['id'] == 'dana.state.alert')
    state['data_port'] = {'id': 'dana.state.alert.port.data', 'mode': 'override', 'bindings': [binding]}
    actor_file.write_text(json.dumps(actor), encoding='utf-8')
    session = Session(story, manifest, project / 'characters', 'recovery')
    try:
        status, data = session.post('/api/data/inspect', id='port:dana.state.alert.port.data')
        if status != 200 or data.get('data_input', {}).get('status') != 'resolved':
            raise RuntimeError('Neutral form profile did not resolve')
        status, response = session.post('/api/compose', provider='venice', beat_id='observe',
                                        state_overrides={'dana': 'dana.state.alert'})
        patches = response.get('patches', [])
        candidate = patches[0] if patches else {}
        return {'http': status, 'provider': candidate.get('provider'),
            'model': candidate.get('model_name'), 'proposal_count': len(patches),
            'eligible': candidate.get('eligible'), 'decision': candidate.get('decision'),
            'state_overrides': candidate.get('state_overrides'),
            'form_profile_resolved': True, 'profile_review_status': 'pending_review',
            'candidate_characters': len(candidate.get('proposed', '')),
            'source_unchanged': story.read_bytes() == before, 'applied': False,
            'error': response.get('error') if status != 200 else None}
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    workspace, out = args.workspace.resolve(), args.out.resolve()
    if out.exists() or out.is_relative_to(workspace):
        raise ValueError('Use a new output folder outside the workspace')
    index = json.loads((workspace / 'timeline.json').read_text(encoding='utf-8'))
    before = snapshot(workspace, index)
    section = next(s for s in index['sections'] if s['id'] == 'climax_tag')
    with tempfile.TemporaryDirectory(prefix='venice-restart-check-') as tmp:
        folder = Path(tmp)
        neutral = neutral_composer(folder)
        scoped, candidates = inspect_case(workspace, folder / 'section', section, True, False)
    after = snapshot(workspace, index)
    out.mkdir(parents=True)
    report = {'neutral_form_composer': neutral, 'scoped_conditioner': scoped['venice'],
              'source_files_unchanged': before == after, 'source_file_count': len(before),
              'proposals_applied': False,
              'note': 'The story target is one hash-pinned, manually reviewed non-explicit passage. The composer fixture is synthetic.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (out / 'conditioner_proposals.json').write_text(json.dumps(candidates, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if before != after:
        raise ValueError('A source file changed during the audit')


if __name__ == '__main__':
    main()
