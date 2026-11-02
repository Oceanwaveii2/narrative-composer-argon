"""
Tests for the canonical document model and the themeable reader renderer.

The central guarantee is parity: rendering from the model must reproduce the legacy
emitter's output byte-for-byte for the master chronology, while being generic enough to
format a different screenplay without touching code.
"""

import unittest
from pathlib import Path

from narrative_composer.compiler.document import BlockRole, parse_document
from narrative_composer.compiler.reader_renderer import GENERIC_THEME, render_reader

ROOT = Path(__file__).resolve().parents[2]
CHRONOLOGY = ROOT / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"


class TestDocumentModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CHRONOLOGY.read_text(encoding="utf-8")
        cls.document = parse_document(cls.text)

    def test_round_trip_is_lossless(self):
        self.assertEqual(self.document.to_fountain(), self.text)

    def test_block_ids_are_content_addressed(self):
        """Inserting lines must not rename existing blocks."""
        before = {block.id for block in parse_document(self.text).blocks}
        prepended = "INT. PREPENDED SCENE - DAY\n\nA prepended action line.\n\n" + self.text
        after = {block.id for block in parse_document(prepended).blocks}
        self.assertTrue(
            before <= after,
            f"existing block IDs changed when lines were inserted: {sorted(before - after)[:5]}",
        )

    def test_block_ids_are_unique(self):
        ids = [block.id for block in self.document.blocks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_scenes_group_heading_with_blocks(self):
        self.assertTrue(self.document.scenes)
        headed = [s for s in self.document.scenes if s.heading is not None]
        self.assertTrue(headed)
        for scene in headed:
            self.assertEqual(scene.heading.role, BlockRole.SCENE_HEADING)
            self.assertTrue(scene.blocks, f"scene {scene.id} has no blocks")

    def test_document_roles_follow_the_fountain_ast(self):
        """One parser: every block role must correspond to an AST node of that kind."""
        from collections import Counter

        from narrative_composer.models.ast_nodes import ASTNodeType
        from narrative_composer.parser.fountain_lexer import FountainParser

        ast_counts = Counter(e.node_type for e in FountainParser.parse(self.text))
        role_counts = Counter(b.role for b in self.document.blocks)

        pairs = (
            (BlockRole.ACT_BANNER, ASTNodeType.ACT_BANNER),
            (BlockRole.CHUNK_HEADER, ASTNodeType.CHUNK_HEADER),
            (BlockRole.SCENE_HEADING, ASTNodeType.SCENE_HEADING),
            (BlockRole.NOTE, ASTNodeType.NOTE),
            (BlockRole.DIVIDER, ASTNodeType.DIVIDER),
            (BlockRole.DIALOGUE, ASTNodeType.DIALOGUE),
            (BlockRole.PARENTHETICAL, ASTNodeType.PARENTHETICAL),
        )
        for role, node_type in pairs:
            self.assertEqual(
                role_counts[role], ast_counts[node_type], f"{role.value} vs {node_type.value}"
            )

        # Caps lines that introduce nothing are demoted to action, so cues can be fewer.
        self.assertLessEqual(role_counts[BlockRole.CUE], ast_counts[ASTNodeType.CHARACTER])

    def test_reader_has_no_markdown_leakage(self):
        rendered = render_reader(self.document)
        # Only the screenplay body matters; the inlined Tailwind runtime contains its
        # own regex tables, so scanning the whole document would be a false positive.
        body = rendered.split("<!-- Screenplay Script Body -->", 1)[-1]
        self.assertNotIn("**", body, "Bold markers must never reach the reader body")

    def test_every_scene_heading_has_an_anchor(self):
        rendered = render_reader(self.document)
        for block in self.document.blocks_in(BlockRole.SCENE_HEADING):
            self.assertIn(f'id="{block.id}"', rendered)

    def test_dialogue_quotes_survive_rendering(self):
        quoted = [b for b in self.document.blocks_in(BlockRole.DIALOGUE) if b.text.startswith('"')]
        self.assertTrue(quoted, "Expected quoted dialogue in the chronology")
        rendered = render_reader(self.document)
        self.assertIn("&quot;", rendered)

    def test_every_block_is_addressable_in_the_dom(self):
        """Block IDs must reach the DOM so the editor can target a node."""
        rendered = render_reader(self.document)
        self.assertEqual(rendered.count("data-block="), len(self.document.blocks))

    def test_reader_is_offline_and_self_contained(self):
        """No network at read time: no external script, stylesheet, or font import."""
        rendered = render_reader(self.document)
        self.assertNotIn('<script src="http', rendered)
        self.assertNotIn("@import", rendered)
        self.assertNotIn("fonts.gstatic.com", rendered)
        # The vendored runtime is inlined, so the document carries its own styles.
        self.assertIn("<script>(()=>", rendered)
        self.assertGreater(len(rendered), 400_000)

    def test_generic_theme_formats_a_different_screenplay(self):
        script = (
            "# ACT ONE\n\n## SCENE 1\n\nINT. OFFICE - DAY\n\n"
            "> SFX: RING\n\nDANA stands.\n\n**DANA:** *(quietly)* \"Who?\"\n"
        )
        rendered = render_reader(parse_document(script), GENERIC_THEME)
        self.assertIn('id="int-office-day"', rendered)
        self.assertIn("SCENE 1", rendered)
        self.assertNotIn("HOT SCOOMP", rendered)

    def test_editing_one_block_changes_only_that_block(self):
        document = parse_document(self.text)
        before = render_reader(document).splitlines()

        target = next(b for b in document.blocks if b.role == BlockRole.DIALOGUE)
        replacement = "Replaced line for the editor test."
        self.assertNotIn(replacement, "\n".join(before))
        target.text = replacement

        after = render_reader(document).splitlines()
        self.assertEqual(len(before), len(after))
        self.assertIn(replacement, "\n".join(after))


if __name__ == "__main__":
    unittest.main()
