import tempfile
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from narrative_composer.codex_app_session import CodexAppSession
from narrative_composer.prose.providers.gemini_flash import ProviderExecutionError


class CodexAppSessionTests(unittest.TestCase):
    def test_context_revision_and_automatic_proposal_origin_are_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            session = CodexAppSession(Path(folder) / 'thread.json')
            context = json.dumps({'section': 'story.md', 'revision': 'revision-1'})
            with patch.object(session, '_connect'), patch.object(session, '_turn', return_value='Reply'):
                session.run('Discuss', context=context)
                session.run('Proposal prompt', label='Application proposal request')
            messages = session.snapshot()['messages']
            self.assertEqual(messages[1]['context_section'], 'story.md')
            self.assertEqual(messages[1]['context_revision'], 'revision-1')
            self.assertEqual(messages[3]['kind'], 'proposal')

    def test_chat_is_nonblocking_and_rejects_overlapping_proposal_turns(self):
        with tempfile.TemporaryDirectory() as folder:
            session = CodexAppSession(Path(folder) / 'thread.json')
            entered, release = threading.Event(), threading.Event()
            captured = []
            def turn(prompt, context=None):
                captured.append((prompt, context))
                entered.set()
                release.wait(3)
                return 'A reviewable reply.'
            with patch.object(session, '_connect'), patch.object(session, '_turn', side_effect=turn):
                session.start_chat('Discuss the scene', context='explicit context')
                self.assertTrue(entered.wait(2))
                self.assertTrue(session.snapshot()['running'])
                with self.assertRaises(ProviderExecutionError):
                    session.run('A competing proposal')
                release.set()
                for _ in range(100):
                    if not session.snapshot()['running']:
                        break
                    time.sleep(.01)
                result = session.snapshot()
                self.assertFalse(result['running'])
                self.assertEqual(captured, [('Discuss the scene', 'explicit context')])
                self.assertEqual([m['role'] for m in result['messages']], ['user', 'assistant'])
                self.assertEqual(result['messages'][-1]['text'], 'A reviewable reply.')


if __name__ == '__main__':
    unittest.main()
