"""Cross-process ownership checks using disposable neutral files."""
import hashlib
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from narrative_composer.persistence import WorkspaceConflict, recover_transactions


def _claim_proposal_request(story, start, results):
    from narrative_composer.proposal_store import ProposalStore
    start.wait(10)
    try:
        ProposalStore(Path(story)).claim_request('c'*32, 'same-input')
        results.put('claimed')
    except ValueError:
        results.put('held')


def _write_after_gate(target, journal, start, result, content):
    from narrative_composer.persistence import commit_files
    path = Path(target)
    start.wait(10)
    try:
        commit_files({path: content.encode()}, {str(path.resolve()): hashlib.sha256(b'old').hexdigest()}, Path(journal))
        result.put('committed')
    except WorkspaceConflict:
        result.put('conflict')


def _hold_prepared(target, journal, prepared, release):
    import narrative_composer.persistence as persistence
    original = persistence.write_journal
    def gated(path, data):
        original(path, data)
        if data.get('status') == 'prepared':
            prepared.set()
            if not release.wait(15):
                raise RuntimeError('test gate timed out')
    persistence.write_journal = gated
    path = Path(target)
    persistence.commit_files({path:b'new'}, {str(path.resolve()):hashlib.sha256(b'old').hexdigest()}, Path(journal))


def _recover_after_signal(journal, entered, finished, result):
    entered.set()
    try:
        recover_transactions(Path(journal))
        result.put('recovered')
    except Exception as exc:
        result.put(type(exc).__name__)
    finally:
        finished.set()


def _hold_shared_prepared(target, journal, shared, prepared, release):
    import narrative_composer.persistence as persistence
    original = persistence.write_journal
    def gated(path, data):
        original(path, data)
        if data.get('status') == 'prepared':
            prepared.set()
            if not release.wait(15):
                raise RuntimeError('test gate timed out')
    persistence.write_journal = gated
    path = Path(target)
    persistence.commit_files({path:b'new'}, {str(path.resolve()):hashlib.sha256(b'old').hexdigest()},
                             Path(journal), shared_paths=[Path(shared)])


def _read_shared(target, journal, shared, entered, finished, result):
    from narrative_composer.persistence import workspace_read_snapshot
    entered.set()
    try:
        with workspace_read_snapshot(Path(journal), [Path(shared)]):
            result.put(Path(target).read_text())
    finally:
        finished.set()


class RecoveryConcurrencyTests(unittest.TestCase):
    def test_two_processes_claim_the_same_proposal_request_once(self):
        with tempfile.TemporaryDirectory() as folder:
            story = Path(folder)/'story.md'
            story.write_text('Neutral text.', encoding='utf-8')
            ctx = multiprocessing.get_context('spawn')
            start, results = ctx.Event(), ctx.Queue()
            workers = [ctx.Process(target=_claim_proposal_request, args=(str(story), start, results)) for _ in range(2)]
            for worker in workers: worker.start()
            start.set()
            for worker in workers: worker.join(20)
            self.assertEqual([worker.exitcode for worker in workers], [0, 0])
            self.assertCountEqual([results.get(timeout=2), results.get(timeout=2)], ['claimed', 'held'])
            self.assertEqual(story.read_text(encoding='utf-8'), 'Neutral text.')

    def test_another_edition_cannot_read_shared_data_during_a_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, shared = root/'character.json', root/'characters'
            shared.mkdir()
            target.write_text('old')
            ctx = multiprocessing.get_context('spawn')
            prepared, release, entered, finished = (ctx.Event() for _ in range(4))
            results = ctx.Queue()
            writer = ctx.Process(target=_hold_shared_prepared,
                args=(str(target),str(root/'a.revisions'),str(shared),prepared,release))
            writer.start()
            self.assertTrue(prepared.wait(15))
            reader = ctx.Process(target=_read_shared,
                args=(str(target),str(root/'b.revisions'),str(shared),entered,finished,results))
            reader.start()
            self.assertTrue(entered.wait(10))
            self.assertFalse(finished.wait(.3), 'reader must wait for the shared revision to finish')
            release.set()
            writer.join(15); reader.join(15)
            self.assertEqual((writer.exitcode, reader.exitcode), (0, 0))
            self.assertEqual(results.get(timeout=2), 'new')

    def test_two_processes_with_shared_target_and_distinct_journals_do_not_lose_a_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'shared.json'
            target.write_bytes(b'old')
            ctx = multiprocessing.get_context('spawn')
            start, results = ctx.Event(), ctx.Queue()
            processes = [ctx.Process(target=_write_after_gate, args=(str(target),str(root/f'journal_{i}'),start,results,f'new-{i}')) for i in range(2)]
            for process in processes: process.start()
            start.set()
            outcomes = sorted(results.get(timeout=20) for _ in processes)
            for process in processes:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(outcomes, ['committed','conflict'])
            self.assertIn(target.read_text(), ('new-0','new-1'))

    def test_recovery_waits_for_active_writer_and_recovers_after_process_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, journal = root/'story.md', root/'story.md.revisions'
            target.write_bytes(b'old')
            ctx = multiprocessing.get_context('spawn')
            prepared, release, entered, finished = (ctx.Event() for _ in range(4))
            results = ctx.Queue()
            writer = ctx.Process(target=_hold_prepared,args=(str(target),str(journal),prepared,release))
            writer.start()
            self.assertTrue(prepared.wait(15))
            reader = ctx.Process(target=_recover_after_signal,args=(str(journal),entered,finished,results))
            reader.start()
            self.assertTrue(entered.wait(10))
            self.assertFalse(finished.wait(.3), 'recovery must not roll back an active writer')
            release.set()
            writer.join(15)
            reader.join(15)
            self.assertEqual(writer.exitcode, 0)
            self.assertEqual(reader.exitcode, 0)
            self.assertEqual(results.get(timeout=2), 'recovered')
            self.assertEqual(target.read_bytes(), b'new')

            target.write_bytes(b'old')
            prepared, release = ctx.Event(), ctx.Event()
            writer = ctx.Process(target=_hold_prepared,args=(str(target),str(journal),prepared,release))
            writer.start()
            self.assertTrue(prepared.wait(15))
            writer.terminate()
            writer.join(15)
            recover_transactions(journal)
            self.assertEqual(target.read_bytes(), b'old')
            records = [json.loads(p.read_text()) for p in journal.glob('*/journal.json')]
            self.assertIn('rolled_back', [item['status'] for item in records])

    def test_copied_prepared_journal_cannot_restore_another_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root/'original.md'
            outside.write_bytes(b'current')
            journal = root/'copy.md.revisions'
            entry = journal/'transaction'
            entry.mkdir(parents=True)
            (entry/'0.before').write_bytes(b'old')
            data = {'version':2, 'journal_root':str(root/'original.md.revisions'), 'status':'prepared',
                    'files':[{'path':str(outside), 'backup':'0.before',
                              'before':hashlib.sha256(b'old').hexdigest(),
                              'after':hashlib.sha256(b'current').hexdigest()}]}
            (entry/'journal.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(WorkspaceConflict):
                recover_transactions(journal)
            self.assertEqual(outside.read_bytes(), b'current')


if __name__ == '__main__':
    unittest.main()
