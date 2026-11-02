"""Recoverable multi-artifact commits with optimistic conflict detection.

The filesystem does not offer a multi-file atomic rename. A durable journal keeps
the old bytes until the complete revision is committed. Opening the workspace
rolls back a prepared (interrupted) transaction before reading it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from contextlib import ExitStack, contextmanager
import tempfile
import threading
import time
import uuid

COMMIT_LOCK = threading.RLock()


class WorkspaceConflict(ValueError):
    pass


@contextmanager
def interprocess_locks(paths, timeout=15):
    """Cooperating local processes lock canonical paths in a stable order.

    Lock files live in the local user's temp directory and are never replaced;
    their OS-held locks are released automatically when a process exits.
    This does not coordinate a different machine synchronizing the same files.
    """
    root = Path(tempfile.gettempdir()) / 'narrative_composer_file_locks'
    root.mkdir(parents=True, exist_ok=True)
    keys = sorted({os.path.normcase(str(Path(path).resolve())) for path in paths})
    with ExitStack() as stack:
        for key in keys:
            path = root / (hashlib.sha256(key.encode('utf-8')).hexdigest() + '.lock')
            handle = stack.enter_context(path.open('a+b'))
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'\0')
                handle.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise WorkspaceConflict('A workspace file is busy in another process; try again') from exc
                    time.sleep(.05)
            def release(locked=handle):
                locked.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(locked.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(locked.fileno(), fcntl.LOCK_UN)
            stack.callback(release)
        yield


def ignore_recovery_artifacts(_directory: str, names: list[str]) -> set[str]:
    """Keep path-bearing journals and generated backups out of disposable copies.

    Recovery journal entries contain absolute original paths; replaying a copied
    prepared journal could otherwise restore files outside the sandbox.
    """
    return {name for name in names if name.endswith(('.revisions', '.bak', '.nodes.json'))
            or '.stage-' in name or '.recover-' in name}


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_journal(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + '.pending')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def _rollback(journal, data):
    for entry in data['files']:
        target = Path(entry['path'])
        current = file_hash(target)
        if current not in (entry['before'], entry['after']):
            raise WorkspaceConflict(f'Interrupted save conflicts with external edit: {target.name}')
        if entry['before'] is not None and file_hash(journal.parent / entry['backup']) != entry['before']:
            raise WorkspaceConflict(f'Interrupted save backup is missing or corrupt: {target.name}')
    for entry in data['files']:
        target = Path(entry['path'])
        original = journal.parent / entry['backup']
        if entry['before'] is None:
            target.unlink(missing_ok=True)
        else:
            restore = target.with_name(target.name + '.recover-' + uuid.uuid4().hex)
            restore.write_bytes(original.read_bytes())
            restore.replace(target)
        target.with_name(target.name + '.stage-' + journal.parent.name).unlink(missing_ok=True)
    data['status'] = 'rolled_back'
    write_journal(journal, data)


def _recover_locked(journal_root):
    if not journal_root.exists():
        return
    for journal in sorted(journal_root.glob('*/journal.json')):
        data = json.loads(journal.read_text(encoding='utf-8'))
        if data['status'] != 'prepared':
            continue
        if (data.get('version') != 2 or
                os.path.normcase(data.get('journal_root', '')) != os.path.normcase(str(journal_root.resolve()))):
            raise WorkspaceConflict('Interrupted save has no matching workspace identity; preserve the journal for manual recovery')
        entries = data.get('files')
        if (not isinstance(entries, list) or any(not isinstance(entry, dict) or
                not isinstance(entry.get('path'), str) or not Path(entry['path']).is_absolute() or
                not isinstance(entry.get('backup'), str) or Path(entry['backup']).name != entry['backup'] or
                'before' not in entry or 'after' not in entry for entry in entries)):
            raise WorkspaceConflict('Interrupted save journal is malformed; preserve it for manual recovery')
        targets = [Path(entry['path']) for entry in entries]
        if journal_root.resolve() in (target.resolve() for target in targets):
            raise WorkspaceConflict('Interrupted save journal targets its own workspace lock')
        with interprocess_locks(targets):
            _rollback(journal, data)


def recover_transactions(journal_root: Path, shared_paths=()) -> None:
    journal_root = Path(journal_root).resolve()
    with COMMIT_LOCK, interprocess_locks([journal_root]):
        with interprocess_locks(shared_paths):
            _recover_locked(journal_root)


@contextmanager
def workspace_read_snapshot(journal_root: Path, shared_paths=()):
    """Hold the same journal/shared-data ownership as an editor commit while loading."""
    journal_root = Path(journal_root).resolve()
    with COMMIT_LOCK, interprocess_locks([journal_root]):
        with interprocess_locks(shared_paths):
            _recover_locked(journal_root)
            yield


def commit_files(updates: dict[Path, bytes], expected: dict[str, str | None], journal_root: Path,
                 shared_paths=()) -> None:
    journal_root = Path(journal_root).resolve()
    with COMMIT_LOCK, interprocess_locks([journal_root]):
        with interprocess_locks(shared_paths):
            _recover_locked(journal_root)
            resolved_updates = {p.resolve(): data for p, data in updates.items()}
            if len(resolved_updates) != len(updates):
                raise WorkspaceConflict('Multiple save targets resolve to the same file')
            updates = resolved_updates
            normalized_expected = {str(Path(path).resolve()): digest for path, digest in expected.items()}
            if len(normalized_expected) != len(expected):
                raise WorkspaceConflict('Multiple expected paths resolve to the same file')
            expected = normalized_expected
            if any(str(path) not in expected for path in updates):
                raise WorkspaceConflict('Every save target needs an expected prior hash')
            if journal_root in updates or str(journal_root) in expected:
                raise WorkspaceConflict('A save cannot overwrite its own recovery journal')
            if {Path(p).resolve() for p in shared_paths} & ({*updates} | {Path(p) for p in expected}):
                raise WorkspaceConflict('Shared workspace locks must not also be individual save targets')
            with interprocess_locks([*updates, *expected]):
                _commit_locked(updates, expected, journal_root)


def _commit_locked(updates, expected, journal_root):
        def check():
            for path, digest in expected.items():
                if file_hash(Path(path)) != digest:
                    raise WorkspaceConflict(f'File changed outside this session: {Path(path).name}; reload before saving')
        check()
        tx = journal_root / uuid.uuid4().hex
        tx.mkdir(parents=True)
        entries = []
        staged = []
        journal = tx / 'journal.json'
        try:
            for number, (path, content) in enumerate(updates.items()):
                path.parent.mkdir(parents=True, exist_ok=True)
                backup = f'{number}.before'
                before = file_hash(path)
                if before is not None:
                    with (tx / backup).open('wb') as stream:
                        stream.write(path.read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                temp = path.with_name(path.name + '.stage-' + tx.name)
                with temp.open('wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                staged.append(temp)
                entries.append({'path': str(path), 'backup': backup, 'before': before,
                                'after': hashlib.sha256(content).hexdigest()})
            check()
            data = {'version': 2, 'journal_root': str(journal_root), 'status': 'prepared', 'files': entries}
            write_journal(journal, data)
            for temp, path in zip(staged, updates):
                temp.replace(path)
            data['status'] = 'committed'
            write_journal(journal, data)
        except Exception:
            if journal.exists():
                data = json.loads(journal.read_text(encoding='utf-8'))
                if data.get('status') == 'prepared':
                    _rollback(journal, data)
            raise
        finally:
            for temp in staged:
                temp.unlink(missing_ok=True)
