"""A source variant must remain distinct and preserve its input and projection."""
import json
import tempfile
import unittest
from pathlib import Path

from docx import Document

from narrative_composer.corpus import add_word_variant


class WordVariantTests(unittest.TestCase):
    def test_add_variant_keeps_source_and_unrelated_section_and_records_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'workspace'
            (root / 'sources').mkdir(parents=True)
            original = root / 'existing.md'
            original.write_bytes(b'Existing story\r\n')
            manifest = root / 'existing.manifest.json'
            manifest.write_text('{}', encoding='utf-8')
            index = {'schema_version': 1, 'sources': {}, 'sections': [
                {'id': 'existing', 'story': original.name, 'manifest': manifest.name, 'canon': 'x'}]}
            (root / 'timeline.json').write_text(json.dumps(index), encoding='utf-8')
            source = Path(directory) / 'new.docx'
            doc = Document()
            paragraph = doc.add_paragraph()
            paragraph.add_run('STELLA').bold = True
            paragraph.add_run('\nHello, 世界.')
            doc.add_paragraph('A second paragraph.')
            doc.save(source)
            source_bytes = source.read_bytes()

            section = add_word_variant(root, source, 'variant_one')
            projection = (root / section['story']).read_bytes().decode('utf-8')
            extracted = json.loads((root / 'variant_one.extraction.json').read_text(encoding='utf-8'))
            for item in extracted['paragraphs']:
                self.assertEqual(item['text'], projection[item['projection_char_start']:item['projection_char_end']])
            self.assertTrue(extracted['paragraphs'][0]['runs'][0]['bold'])
            self.assertEqual((root / 'sources' / 'variant_one_docx.docx').read_bytes(), source_bytes)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(original.read_bytes(), b'Existing story\r\n')
            self.assertEqual([s['id'] for s in json.loads((root / 'timeline.json').read_text(encoding='utf-8'))['sections']],
                             ['existing', 'variant_one'])
            before = (root / 'timeline.json').read_bytes(), (root / section['story']).read_bytes()
            with self.assertRaises(FileExistsError):
                add_word_variant(root, source, 'variant_one')
            self.assertEqual(before, ((root / 'timeline.json').read_bytes(), (root / section['story']).read_bytes()))

    def test_invalid_id_does_not_touch_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / 'timeline.json'
            index.write_text('{"sections": [], "sources": {}}', encoding='utf-8')
            before = index.read_bytes()
            with self.assertRaises(ValueError):
                add_word_variant(root, root / 'missing.docx', '../escape')
            self.assertEqual(index.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
