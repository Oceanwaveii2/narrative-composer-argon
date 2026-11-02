"""Document integrity and proposal boundaries for the Tiptap editor."""
import copy
import json
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from docx import Document

from narrative_composer.corpus import word_story_projection
from narrative_composer.editor import EditorHandler
from narrative_composer.persistence import WorkspaceConflict
from narrative_composer.rich_document import (load_document, new_document, sidecar_path,
                                               validate_document)
from narrative_composer.store import to_text


FIXTURE = Path(__file__).parent / 'fixtures' / 'recovery_project'


class RichDocumentTests(unittest.TestCase):
    def test_strict_schema_preserves_unicode_and_rejects_unknown_content(self):
        source = 'One  \r\n\r\n世界 😀\r\n'
        doc = new_document(source)
        self.assertTrue(validate_document(doc, source))
        duplicate = copy.deepcopy(doc)
        duplicate['content'][1]['attrs']['id'] = duplicate['content'][0]['attrs']['id']
        with self.assertRaises(ValueError):
            validate_document(duplicate, source)
        unsupported = copy.deepcopy(doc)
        unsupported['content'][0]['content'][0]['marks'] = [{'type': 'link', 'attrs': {'href': 'x'}}]
        with self.assertRaises(ValueError):
            validate_document(unsupported, source)
        with self.assertRaises(WorkspaceConflict):
            validate_document(doc, source + 'changed')

    def test_word_run_marks_import_only_when_source_spans_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'word.docx'
            word = Document()
            p = word.add_paragraph()
            p.add_run('Bold').bold = True
            p.add_run('\nitalic 世界').italic = True
            word.add_paragraph('Unmarked')
            word.save(original)
            projection, extraction = word_story_projection(original.read_bytes())
            story = root / 'story.md'
            story.write_bytes(projection.encode('utf-8'))
            (root / 'story.extraction.json').write_text(json.dumps(extraction, ensure_ascii=False), encoding='utf-8')
            document, status = load_document(story, projection)
            self.assertEqual(status, 'word_import')
            self.assertEqual(document['content'][0]['content'][0]['marks'], [{'type': 'bold'}])
            self.assertEqual(document['content'][1]['content'][0]['marks'], [{'type': 'italic'}])
            self.assertTrue(validate_document(document, projection))
            changed, status = load_document(story, projection.replace('Bold', 'Edited'))
            self.assertEqual(status, 'new')
            self.assertTrue(validate_document(changed, projection.replace('Bold', 'Edited')))


class RichEditorHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        shutil.copytree(FIXTURE, self.root)
        self.source = self.root / 'story.md'
        self.manifest = self.root / 'manifest.json'

    def start(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), EditorHandler)
        self.server.screenplay_path = self.source
        self.server.manifest_path = self.manifest
        self.server.entity_dir = self.root / 'characters'
        self.server.canon = 'recovery'
        self.server.store = None
        self.server.store_text = None
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        return self.get('/api/source')[1]

    def get(self, route):
        try:
            with urlopen(self.url + route) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def post(self, route, **payload):
        request = Request(self.url + route, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_save_reload_crlf_and_conflicting_external_sidecar(self):
        raw = self.source.read_text(encoding='utf-8').replace('\n', '\r\n').encode('utf-8')
        self.source.write_bytes(raw)
        initial = self.start()
        text, document = initial['text'], initial['rich_document']
        document['content'][0]['content'][0]['marks'] = [{'type': 'bold'}]
        status, saved = self.post('/api/save', text=text, revision=initial['revision'], rich_document=document)
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.source.read_bytes(), raw)
        status, loaded = self.get('/api/source?reload=1')
        self.assertEqual(status, 200, loaded)
        self.assertEqual(loaded['rich_document'], document)
        self.assertEqual(loaded['rich_status'], 'saved')
        sidecar = sidecar_path(self.source)
        sidecar.write_bytes(sidecar.read_bytes() + b' ')
        status, result = self.post('/api/save', text=text, revision=loaded['revision'], rich_document=document)
        self.assertEqual(status, 409, result)
        self.assertEqual(self.source.read_bytes(), raw)
        status, legacy = self.post('/api/save', text=text, revision=loaded['revision'])
        self.assertEqual(status, 409, legacy)

    def test_external_source_change_blocks_loading_saved_formatting(self):
        initial = self.start()
        text, document = initial['text'], initial['rich_document']
        status, result = self.post('/api/save', text=text, revision=initial['revision'], rich_document=document)
        self.assertEqual(status, 200, result)
        changed = self.source.read_bytes() + b'External change.'
        self.source.write_bytes(changed)
        status, result = self.get('/api/source?reload=1')
        self.assertEqual(status, 409, result)
        self.assertEqual(self.source.read_bytes(), changed)

    def test_repair_preview_and_formatting_staleness_do_not_mutate_story(self):
        self.source.write_text('INT. HALL - DAY\n\nThe Hot Scoomp poster hangs crooked.\n', encoding='utf-8')
        initial = self.start()
        text, rev, document = initial['text'], initial['revision'], initial['rich_document']
        status, planned = self.post('/api/recook', text=text, revision=rev, rich_document=document, provider='mock')
        self.assertEqual(status, 200, planned)
        proposal = planned['patches'][0]
        changed_format = copy.deepcopy(document)
        changed_format['content'][2]['content'][0]['marks'] = [{'type': 'italic'}]
        status, stale = self.post('/api/proposal/apply', text=text, revision=rev, rich_document=changed_format,
                                  proposal_id=proposal['proposal_id'], reviewed=True)
        self.assertEqual(status, 409, stale)
        self.assertEqual(to_text(self.server.store), text)
        status, preview = self.post('/api/proposal/apply', text=text, revision=rev, rich_document=document,
                                    proposal_id=proposal['proposal_id'], reviewed=True, preview_only=True)
        self.assertEqual(status, 200, preview)
        self.assertNotEqual(preview['text'], text)
        self.assertEqual(to_text(self.server.store), text)
        self.assertFalse(self.server.store.meta.get('decisions'))
        status, applied = self.post('/api/proposal/apply', text=text, revision=rev, rich_document=document,
                                    proposal_id=proposal['proposal_id'], reviewed=True)
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied['text'], preview['text'])
        self.assertEqual(self.source.read_bytes().decode('utf-8'), text)

    def test_formatting_only_draft_cannot_switch_timeline(self):
        other = self.root / 'other.md'
        other.write_text('INT. OTHER - DAY\n', encoding='utf-8')
        other_manifest = self.root / 'other.manifest.json'
        shutil.copy2(self.manifest, other_manifest)
        timeline = self.root / 'timeline.json'
        timeline.write_text(json.dumps({'sections': [
            {'id': 'first', 'story': self.source.name, 'manifest': self.manifest.name, 'canon': 'recovery'},
            {'id': 'second', 'story': other.name, 'manifest': other_manifest.name, 'canon': 'recovery'}]}), encoding='utf-8')
        initial = self.start()
        self.server.timeline_path = timeline
        document = copy.deepcopy(initial['rich_document'])
        document['content'][0]['attrs']['align'] = 'center'
        status, result = self.post('/api/timeline/open', text=initial['text'], revision=initial['revision'],
                                   rich_document=document, id='second')
        self.assertEqual(status, 409, result)
        self.assertEqual(self.server.screenplay_path, self.source)

    def test_composed_beat_appends_without_trimming_source_whitespace(self):
        original = self.source.read_bytes() + b'\r\n\r\n'
        self.source.write_bytes(original)
        initial = self.start()
        text, rev, document = initial['text'], initial['revision'], initial['rich_document']
        status, plan = self.post('/api/compose', text=text, revision=rev, rich_document=document, provider='mock')
        self.assertEqual(status, 200, plan)
        proposal = plan['patches'][0]
        status, preview = self.post('/api/proposal/apply', text=text, revision=rev, rich_document=document,
                                    proposal_id=proposal['proposal_id'], reviewed=True, preview_only=True)
        self.assertEqual(status, 200, preview)
        self.assertTrue(preview['text'].startswith(text))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.server.store.meta.get('manifest_dirty'))

    def test_author_beat_is_validated_unsaved_and_survives_save_reload(self):
        manifest = json.loads(self.manifest.read_text(encoding='utf-8'))
        manifest['beats'] = {}
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        original_manifest, original_story = self.manifest.read_bytes(), self.source.read_bytes()
        initial = self.start()
        text, rev, document = initial['text'], initial['revision'], initial['rich_document']
        document['content'][0]['content'][0]['marks'] = [{'type': 'bold'}]
        common = {'text': text, 'revision': rev, 'rich_document': document,
                  'slugline': 'INT. HALL - DAY', 'dramatic_goal': 'Dana considers the next step.',
                  'active_characters': ['dana'], 'beat_id': 'author_beat'}
        status, invalid = self.post('/api/beat/create', **dict(common, active_characters=['unknown']))
        self.assertEqual(status, 400, invalid)
        status, invalid = self.post('/api/beat/create', **dict(common, dramatic_goal='  '))
        self.assertEqual(status, 400, invalid)
        status, created = self.post('/api/beat/create', **common)
        self.assertEqual(status, 200, created)
        self.assertEqual(created['beat']['active_characters'], ['dana'])
        self.assertEqual(created['status'], 'unsaved author plan')
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertEqual(self.source.read_bytes(), original_story)
        status, stale = self.post('/api/beat/create', **common)
        self.assertEqual(status, 409, stale)
        rev = created['revision']
        status, duplicate = self.post('/api/beat/create', **dict(common, revision=rev))
        self.assertEqual(status, 400, duplicate)
        status, planned = self.post('/api/compose', text=text, revision=rev, rich_document=document, provider='mock')
        self.assertEqual(status, 200, planned)
        self.assertEqual(planned['patches'][0]['beat_id'], 'author_beat')
        self.assertEqual(self.source.read_bytes(), original_story)
        status, saved = self.post('/api/save', text=text, revision=rev, rich_document=document)
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.source.read_bytes(), original_story)
        self.assertEqual(json.loads(self.manifest.read_text(encoding='utf-8'))['beats']['author_beat']['dramatic_goal'],
                         'Dana considers the next step.')
        status, loaded = self.get('/api/source?reload=1')
        self.assertEqual(status, 200, loaded)
        self.assertEqual(loaded['rich_document'], document)
        status, planned = self.post('/api/compose', text=text, revision=loaded['revision'],
                                    rich_document=document, provider='mock')
        self.assertEqual(status, 200, planned)
        self.assertEqual(planned['patches'][0]['beat_id'], 'author_beat')

    def test_selected_new_beat_does_not_redraft_existing_incomplete_beat(self):
        initial = self.start()
        text, doc, rev = initial['text'], initial['rich_document'], initial['revision']
        status, created = self.post('/api/beat/create', text=text, revision=rev, rich_document=doc,
            slugline='INT. HALL - DAY', dramatic_goal='Dana checks the latch.', active_characters=['dana'],
            beat_id='new_author_beat')
        self.assertEqual(status, 200, created)
        status, beats = self.post('/api/beats', text=text, revision=created['revision'], rich_document=doc)
        self.assertEqual(status, 200, beats)
        self.assertEqual([b['beat_id'] for b in beats['beats']], ['observe', 'new_author_beat'])
        status, plan = self.post('/api/compose', text=text, revision=created['revision'], rich_document=doc,
                                 provider='mock', beat_id='new_author_beat')
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan['patches'][0]['beat_id'], 'new_author_beat')
        self.assertEqual(self.source.read_bytes().decode('utf-8'), text)

    def test_codex_chat_sends_only_explicit_context_and_preserves_source(self):
        class FakeSession:
            def __init__(self):
                self.calls = []
            def start_connect(self):
                pass
            def start_chat(self, message, context):
                self.calls.append((message, context))
            def snapshot(self):
                return {'messages': [], 'running': False}
        initial = self.start()
        fake = self.server.codex_session = FakeSession()
        text, doc, rev = initial['text'], initial['rich_document'], initial['revision']
        original = self.source.read_bytes()
        status, result = self.post('/api/codex/send', text=text, revision=rev, rich_document=doc,
                                   message='Discuss the scene', context='none')
        self.assertEqual(status, 200, result)
        self.assertIsNone(fake.calls[-1][1])
        status, result = self.post('/api/codex/send', text=text, revision=rev, rich_document=doc,
                                   message='Discuss the scene', context='document')
        self.assertEqual(status, 200, result)
        context = json.loads(fake.calls[-1][1])
        self.assertEqual(context['story_text'], text)
        self.assertIn('dana', context['characters'])
        self.assertIn('observe', context['manifest']['beats'])
        self.assertEqual(self.source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
