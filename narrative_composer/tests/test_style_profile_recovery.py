"""Regression checks for the retired rating profile and preserved authored data."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from narrative_composer.cli import cmd_prose_rewrite
from narrative_composer.compiler.document import BlockRole, parse_document
from narrative_composer.compiler.reader_renderer import GENERIC_THEME, HOT_SCOOMP_THEME, render_reader
from narrative_composer.compiler.recook_dispatcher import ProseRecooker
from narrative_composer.condition import plan_conditioning
from narrative_composer.prose.approved_edits import ApprovedEditPair, ApprovedEditsStore
from narrative_composer.prose.style_engine import StyleProfileRepository


class CapturingProvider:
    model_name = 'capture'

    def __init__(self):
        self.calls = []

    def generate_rewrite(self, request, prompt):
        self.calls.append((request, prompt))
        return request.original_text


class StyleProfileRecoveryTests(unittest.TestCase):
    def test_recook_and_conditioning_use_the_standard_profile(self):
        provider = CapturingProvider()
        recooker = ProseRecooker(provider=provider)
        recooker.recook_span('A person opens the door.', SimpleNamespace(line_number=1))

        text = 'INT. ROOM - DAY\n\nA person opens the door.\n'
        document = parse_document(text)
        action = next(block for block in document.blocks if block.role == BlockRole.ACTION)
        plan_conditioning(text, provider, document=document, target_block_ids=[action.id])

        self.assertEqual(len(provider.calls), 2)
        for request, prompt in provider.calls:
            self.assertEqual(request.style_profile_id, 'standard_dramatic')
            self.assertNotIn('TV-14', prompt)
            self.assertNotIn('gratuitous explicit content', prompt)

    def test_legacy_cli_profile_falls_back_to_standard_with_notice(self):
        provider = CapturingProvider()
        output = StringIO()
        with patch('narrative_composer.cli.create_prose_provider', return_value=provider):
            with redirect_stdout(output):
                cmd_prose_rewrite('A person opens the door.', profile_id='hot_scoomp_tv14')
        self.assertIn('using standard_dramatic', output.getvalue())
        request, prompt = provider.calls[0]
        self.assertEqual(request.style_profile_id, 'standard_dramatic')
        self.assertNotIn('TV-14', prompt)

    def test_existing_legacy_edits_remain_readable_and_unchanged(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'edits.json'
            store = ApprovedEditsStore(storage_path=str(path))
            store.add_edit(ApprovedEditPair(edit_id='old-edit', profile_id='hot_scoomp_tv14',
                                           original_text='Original sentence.',
                                           approved_text='Approved sentence.'))
            before = path.read_bytes()
            self.assertIsNone(StyleProfileRepository().get_style_profile('hot_scoomp_tv14'))
            reloaded = ApprovedEditsStore(storage_path=str(path))
            edits = reloaded.retrieve_relevant_edits('hot_scoomp_tv14', 'Original sentence.')
            self.assertEqual([item.edit_id for item in edits], ['old-edit'])
            self.assertEqual(path.read_bytes(), before)

    def test_reader_header_does_not_replace_authored_rating_text(self):
        document = parse_document('INT. ROOM - DAY\n\nThe notice says TV-14 Animated Comedy.\n')
        generic = render_reader(document, GENERIC_THEME)
        themed = render_reader(document, HOT_SCOOMP_THEME)
        self.assertIn('The notice says TV-14 Animated Comedy.', generic)
        self.assertIn('The notice says TV-14 Animated Comedy.', themed)
        self.assertIn('<span>Authored draft</span>', generic)
        self.assertIn('<span>Animated Comedy</span>', themed)
        self.assertNotIn('<span>TV-14 Animated Comedy</span>', themed)


if __name__ == '__main__':
    unittest.main()
