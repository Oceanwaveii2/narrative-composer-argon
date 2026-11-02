"""Bounded provider integration check on a disposable, non-story fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reproductions.audit_timeline_pipeline import Session
from narrative_composer.compiler.document import BlockRole
from narrative_composer.store import document_from_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('deepseek', 'venice', 'gemini_session'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Choose a new output file')
    fixture = Path(__file__).resolve().parents[1] / 'narrative_composer/tests/fixtures/recovery_project'
    with tempfile.TemporaryDirectory(prefix='narrative-neutral-provider-') as temporary:
        project = Path(temporary) / 'project'
        shutil.copytree(fixture, project)
        story = project / 'story.md'
        original = story.read_bytes()
        session = Session(story, project / 'manifest.json', project / 'characters', 'recovery')
        session.server.gemini_state_dir = project / 'gemini-state'
        session.server.deepseek_state_dir = project / 'deepseek-state'
        try:
            action = next(block for block in document_from_store(session.server.store).blocks
                          if block.role == BlockRole.ACTION and 'Dana locks the door' in block.text)
            status, conditioned = session.post('/api/condition', provider=args.provider,
                                               limit=1, target_block_ids=[action.id])
            patches = conditioned.get('patches', [])
            condition = {'http':status, 'proposal_count':len(patches),
                         'proposals':[{'eligible':p.get('eligible'), 'reason':p.get('reason'),
                                      'original':p.get('original'), 'proposed':p.get('proposed'),
                                      'attempt_reasons':p.get('attempt_reasons'),
                                      'source_revision':p.get('base_revision'),
                                      'graph_context_present':bool(p.get('graph_context'))} for p in patches],
                         'error':conditioned.get('error')}
            status, composed = session.post('/api/compose', provider=args.provider, beat_id='observe')
            patches = composed.get('patches', [])
            composition = {'http':status, 'proposal_count':len(patches),
                           'proposals':[{'eligible':p.get('eligible'), 'reason':p.get('rationale'),
                                        'proposed':p.get('proposed'), 'validation':p.get('validation'),
                                        'authored_evidence_count':len(p.get('authored_evidence', []))}
                                        for p in patches], 'error':composed.get('error')}
            result = {'provider':args.provider, 'scope':'neutral disposable fixture; no authored story',
                      'conditioner':condition, 'composer':composition,
                      'source_unchanged':story.read_bytes() == original,
                      'source_sha256':hashlib.sha256(original).hexdigest(),
                      'notice':'Candidates require human review; no proposal was applied.'}
        finally:
            session.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'provider':args.provider, 'condition_http':condition['http'],
                      'condition_candidates':condition['proposal_count'],
                      'condition_eligible':sum(bool(p['eligible']) for p in condition['proposals']),
                      'compose_http':composition['http'], 'compose_candidates':composition['proposal_count'],
                      'source_unchanged':result['source_unchanged']}), flush=True)


if __name__ == '__main__':
    main()
