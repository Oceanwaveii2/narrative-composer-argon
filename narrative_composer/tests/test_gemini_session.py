"""Neutral tests for the signed-in Gemini session bridge; no live provider calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from narrative_composer.gemini_session import GeminiCliSession, GeminiSessionProvider
from narrative_composer.prose.providers.gemini_flash import ProviderExecutionError

CONVERSATION = '12345678-1234-4234-8234-123456789abc'


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.tool_event = False
        self.status = 'SUCCESS'

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        events = [{'event':'init', 'conversation_id':CONVERSATION}]
        if self.tool_event:
            events.append({'event':'step_update', 'step_update':{'step_type':'tool'}})
        events.append({'event':'result','result':{'conversation_id':CONVERSATION,
                       'status':self.status,'response':'A neutral draft.'}})
        return subprocess.CompletedProcess(args, 0, stdout='\n'.join(json.dumps(x) for x in events), stderr='')


class GeminiSessionTests(unittest.TestCase):
    def test_session_uses_stdin_denies_tools_and_resumes_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'session.json'
            runner = FakeRunner()
            session = GeminiCliSession(path, executable='agy.exe', runner=runner)
            provider = GeminiSessionProvider(session)
            self.assertEqual(provider.generate_rewrite(None, 'Private neutral prompt'), 'A neutral draft.')
            args, options = runner.calls[0]
            self.assertNotIn('Private neutral prompt', ' '.join(args))
            self.assertIn('Private neutral prompt', options['input'])
            settings = json.loads(args[args.index('--settings')+1])
            self.assertIn('write_file(*)', settings['permissions']['deny'])
            self.assertIn('command(*)', settings['permissions']['deny'])
            self.assertIn('mcp(*)', settings['permissions']['deny'])
            self.assertTrue(Path(options['cwd']).is_dir())
            reopened = GeminiCliSession(path, executable='agy.exe', runner=runner)
            self.assertEqual(reopened.run('Next turn'), 'A neutral draft.')
            self.assertEqual(runner.calls[1][0][runner.calls[1][0].index('--conversation')+1], CONVERSATION)
            self.assertEqual(len(reopened.snapshot()['messages']), 4)

    def test_tool_use_and_failed_or_malformed_results_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = FakeRunner(); runner.tool_event = True
            session = GeminiCliSession(Path(temp)/'session.json', executable='agy.exe', runner=runner)
            with self.assertRaisesRegex(ProviderExecutionError, 'tool operation'):
                session.run('neutral')
            self.assertFalse(session.path.exists())
            runner.tool_event = False; runner.status = 'ERROR'
            with self.assertRaisesRegex(ProviderExecutionError, 'did not complete'):
                session.run('neutral')
            self.assertFalse(session.path.exists())

    def test_completed_result_survives_cli_shutdown_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            result = {'event':'result','result':{'conversation_id':CONVERSATION,
                      'status':'SUCCESS','response':'A neutral draft.'}}
            def timeout(args, **kwargs):
                raise subprocess.TimeoutExpired(args, 100, output=json.dumps(result).encode('utf-8'))
            session = GeminiCliSession(Path(temp)/'session.json', executable='agy.exe', runner=timeout)
            self.assertEqual(session.run('neutral'), 'A neutral draft.')
            self.assertTrue(session.path.exists())

    def test_success_with_empty_response_preserves_prior_session(self):
        # The live CLI has returned SUCCESS with no agent response or text.
        # Treat that envelope as a failed turn and retain the saved history.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'session.json'
            session = GeminiCliSession(path, executable='agy.exe', runner=FakeRunner())
            session.run('first turn')
            original = path.read_bytes()
            result = {'event':'result', 'result':{'conversation_id':CONVERSATION,
                      'status':'SUCCESS', 'response':''}}
            session.runner = lambda args, **kwargs: subprocess.CompletedProcess(
                args, 0, stdout=json.dumps(result), stderr='')
            with self.assertRaisesRegex(ProviderExecutionError, 'returned no text'):
                session.run('second turn')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(session.snapshot()['messages']), 2)
            self.assertIn('returned no text', session.snapshot()['error'])
            self.assertFalse(session.snapshot()['running'])

    def test_incomplete_timeout_preserves_prior_session_and_exposes_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'session.json'
            session = GeminiCliSession(path, executable='agy.exe', runner=FakeRunner())
            session.run('first turn')
            original = path.read_bytes()
            def incomplete(args, **kwargs):
                partial = json.dumps({'event':'init', 'conversation_id':CONVERSATION})
                raise subprocess.TimeoutExpired(args, 100, output=partial.encode('utf-8'))
            session.runner = incomplete
            with self.assertRaisesRegex(ProviderExecutionError, 'timed out before completing'):
                session.run('second turn')
            self.assertEqual(path.read_bytes(), original)
            self.assertIn('timed out', session.snapshot()['error'])
            self.assertFalse(session.snapshot()['running'])

    def test_real_subprocess_timeout_with_partial_output_is_not_an_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            def slow_process(args, **kwargs):
                kwargs['timeout'] = 0.4
                return subprocess.run([sys.executable, '-c',
                    'import time; print("{\\\"event\\\":\\\"init\\\"}", flush=True); time.sleep(5)'], **kwargs)
            session = GeminiCliSession(Path(temp)/'session.json', executable='agy.exe', runner=slow_process)
            with self.assertRaisesRegex(ProviderExecutionError, 'timed out before completing'):
                session.run('neutral')
            self.assertFalse(session.path.exists())

    def test_unsaved_answer_remains_visible_and_blocks_another_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            session = GeminiCliSession(Path(temp)/'session.json', executable='agy.exe', runner=FakeRunner())
            with patch.object(session, '_persist', side_effect=OSError('disk full')):
                self.assertEqual(session.run('neutral'), 'A neutral draft.')
            self.assertIn('not saved', session.snapshot()['error'])
            self.assertEqual(session.snapshot()['messages'][-1]['text'], 'A neutral draft.')
            with self.assertRaisesRegex(ProviderExecutionError, 'not saved'):
                session.run('another turn')


if __name__ == '__main__':
    unittest.main()
