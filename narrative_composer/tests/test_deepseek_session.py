import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from narrative_composer.deepseek_session import DeepSeekSession
from narrative_composer.prose.providers import create_prose_provider
from narrative_composer.prose.providers.deepseek import DeepSeekProseProvider
from narrative_composer.prose.providers.gemini_flash import ProviderConfigurationError, ProviderExecutionError
from narrative_composer.prose.providers.venice import VeniceProseProvider


class Response:
    def __init__(self, finish='stop', text='A neutral answer.', status=200):
        self.status_code, self.finish, self.text = status, finish, text
    def json(self):
        return {'choices':[{'finish_reason':self.finish, 'message':{'content':self.text}}]}


class FakeProvider:
    api_key = 'test-only'
    model_name = 'deepseek-flash'
    def __init__(self): self.calls = []
    def chat(self, messages):
        self.calls.append(messages)
        return f'Neutral answer {len(self.calls)}.'


class DeepSeekSessionTests(unittest.TestCase):
    def test_api_transport_and_incomplete_response_do_not_accept_truncated_text(self):
        provider = create_prose_provider('deepseek', api_key='test-only')
        self.assertIsInstance(provider, DeepSeekProseProvider)
        messages = [{'role':'user', 'content':'A neutral question.'}]
        with patch('httpx.post', return_value=Response()) as send:
            self.assertEqual(provider.chat(messages), 'A neutral answer.')
        self.assertEqual(send.call_args.args[0], 'https://api.deepseek.com/chat/completions')
        self.assertEqual(send.call_args.kwargs['json']['messages'], messages)
        for finish in ('length', 'content_filter', 'aborted'):
            with patch('httpx.post', return_value=Response(finish=finish)):
                with self.assertRaises(ProviderExecutionError): provider.chat(messages)
        with patch('httpx.post', return_value=Response(status=401, text='server reflected private data')):
            with self.assertRaises(ProviderExecutionError) as error: provider.chat(messages)
            self.assertNotIn('private data', str(error.exception))
        with patch('narrative_composer.prose.providers.deepseek.load_deepseek_api_key', return_value=None):
            with self.assertRaises(ProviderConfigurationError):
                DeepSeekProseProvider().chat(messages)
        with self.assertRaises(ProviderExecutionError):
            VeniceProseProvider._response_text(Response(finish='length').json())

    def test_history_resumes_and_start_new_archives_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'conversation.json'
            provider = FakeProvider()
            session = DeepSeekSession(path, provider)
            context = json.dumps({'section':'story.md','revision':'one'})
            self.assertEqual(session.run('First question', context=context), 'Neutral answer 1.')
            reopened = DeepSeekSession(path, provider)
            reopened.run('Second question')
            self.assertEqual(len(provider.calls[-1]), 4)  # system, prior user/reply, new user
            self.assertEqual(provider.calls[-1][1]['role'], 'user')
            self.assertEqual(reopened.snapshot()['messages'][1]['context_revision'], 'one')
            before = path.read_bytes()
            reopened.start_new()
            archives = list(Path(folder).glob('conversation.archived-*.json'))
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].read_bytes(), before)
            self.assertFalse(path.exists())
            self.assertEqual(reopened.snapshot()['messages'], [])

    def test_conflicting_session_preserves_the_provider_answer_for_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'conversation.json'
            first, second = DeepSeekSession(path, FakeProvider()), DeepSeekSession(path, FakeProvider())
            first.run('First session')
            accepted = path.read_bytes()
            with self.assertRaisesRegex(ProviderExecutionError, 'response was preserved'):
                second.run('Competing session')
            self.assertEqual(path.read_bytes(), accepted)
            conflicts = list(Path(folder).glob('conversation.conflict-*.json'))
            self.assertEqual(len(conflicts), 1)
            recovery = json.loads(conflicts[0].read_text(encoding='utf-8'))
            self.assertEqual(recovery['history'][-1]['content'], 'Neutral answer 1.')


if __name__ == '__main__':
    unittest.main()
