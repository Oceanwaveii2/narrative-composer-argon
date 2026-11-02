"""Durable, edition-scoped proposals; creating a proposal never edits a story."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3


class ProposalStore:
    def __init__(self, story_path):
        story = Path(story_path).resolve()
        self.path = story.parent / '.narrative_proposals' / (story.name + '.sqlite3')

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute('PRAGMA busy_timeout=15000')
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            connection.close()
            raise ValueError('Proposal history uses an unsupported version; preserve it before recovery')
        connection.execute('CREATE TABLE IF NOT EXISTS proposals (proposal_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS decisions (proposal_id TEXT NOT NULL, action TEXT NOT NULL, '
                           'created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                           'FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id))')
        connection.execute('CREATE TABLE IF NOT EXISTS proposal_requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, '
                           'state TEXT NOT NULL, response TEXT)')
        if version == 0:
            connection.execute('PRAGMA user_version=1')
        connection.commit()
        return connection

    def append(self, changes):
        if not changes:
            return
        rows = [(change['proposal_id'], json.dumps(change, ensure_ascii=False)) for change in changes]
        with closing(self._connect()) as connection:
            with connection:
                connection.executemany('INSERT INTO proposals(proposal_id,payload) VALUES (?,?)', rows)

    def claim_request(self, request_id, fingerprint):
        """Claim a request once, including across processes and restarts."""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute('INSERT OR IGNORE INTO proposal_requests(request_id,fingerprint,state) VALUES (?,?,?)',
                                   (request_id, fingerprint, 'running'))
                created = connection.execute('SELECT changes()').fetchone()[0] == 1
                row = connection.execute('SELECT fingerprint,state,response FROM proposal_requests WHERE request_id=?',
                                         (request_id,)).fetchone()
        if row[0] != fingerprint:
            raise ValueError('Request ID was already used for different input')
        if created:
            return None
        if row[1] == 'complete':
            return json.loads(row[2])
        raise ValueError('This request is running or its outcome is uncertain. Check proposal history before starting a new request.')

    def finish_request(self, request_id, changes, planning=None):
        """Commit proposals and replayable result in the same transaction."""
        rows = [(change['proposal_id'], json.dumps(change, ensure_ascii=False)) for change in changes]
        response = {'patches': changes}
        if planning is not None:
            response['planning'] = planning
        with closing(self._connect()) as connection:
            with connection:
                connection.executemany('INSERT INTO proposals(proposal_id,payload) VALUES (?,?)', rows)
                cursor = connection.execute('UPDATE proposal_requests SET state=?,response=? WHERE request_id=? AND state=?',
                    ('complete', json.dumps(response, ensure_ascii=False), request_id, 'running'))
                if cursor.rowcount != 1:
                    raise ValueError('Proposal request is no longer pending')

    def get(self, identity):
        if not self.path.is_file():
            return None
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT payload, (SELECT action FROM decisions WHERE decisions.proposal_id=proposals.proposal_id '
                                     'ORDER BY decisions.rowid DESC LIMIT 1) FROM proposals WHERE proposal_id=?', (identity,)).fetchone()
        if not row:
            return None
        item = json.loads(row[0])
        item['author_decision'] = row[1] or 'pending'
        return item

    def list(self):
        if not self.path.is_file():
            return []
        with closing(self._connect()) as connection:
            rows = connection.execute('SELECT payload, (SELECT action FROM decisions WHERE decisions.proposal_id=proposals.proposal_id '
                                      'ORDER BY decisions.rowid DESC LIMIT 1) FROM proposals ORDER BY proposals.rowid DESC').fetchall()
        return [dict(json.loads(row[0]), author_decision=row[1] or 'pending') for row in rows]

    def decide(self, identity, action):
        if action not in ('rejected', 'pending'):
            raise ValueError('Unknown proposal decision')
        if not self.path.is_file():
            raise ValueError('Proposal does not exist in this edition')
        with closing(self._connect()) as connection:
            with connection:
                if not connection.execute('SELECT 1 FROM proposals WHERE proposal_id=?', (identity,)).fetchone():
                    raise ValueError('Proposal does not exist in this edition')
                connection.execute('INSERT INTO decisions(proposal_id,action) VALUES (?,?)', (identity, action))
