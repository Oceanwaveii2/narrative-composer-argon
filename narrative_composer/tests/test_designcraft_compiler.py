"""
Unit and Integration Tests for DesignCraft Screenplay Compiler Engine.
Verifies typography invariants, AST mapping, multi-page threading, preflight cleanliness, and PDF generation.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from narrative_composer.designcraft import (
    DesignCraftCompiler,
    DesignCraftDoc,
    Page,
    Spread,
    Story,
)
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.parser.fountain_lexer import FountainParser


@unittest.skip("DesignCraft disabled")
class TestDesignCraftCompiler(unittest.TestCase):
    def setUp(self):
        self.compiler = DesignCraftCompiler()

    def test_models_validation(self):
        """Verify that models serialize to valid camelCase JSON matching DesignCraft schema."""
        page = Page(id=1, width=612.0, height=792.0, x=0.0)
        data = page.model_dump(by_alias=True)
        self.assertEqual(data["width"], 612.0)
        self.assertEqual(data["height"], 792.0)
        self.assertTrue(data["showParentItems"])
        self.assertIn("margins", data)
        self.assertEqual(data["margins"]["inside"], 108.0)

    def test_ast_to_paragraphs_normalization(self):
        """Verify AST elements map to expected screenplay paragraph styles."""
        sample_ast = [
            ASTElement(
                node_type=ASTNodeType.SCENE_HEADING,
                content="INT. THE BUTTON NIGHTCLUB - NIGHT",
            ),
            ASTElement(
                node_type=ASTNodeType.ACTION,
                content="Cigarette smoke swirls under purple neon.",
            ),
            ASTElement(
                node_type=ASTNodeType.CHARACTER,
                content="FRANCINE LING",
            ),
            ASTElement(
                node_type=ASTNodeType.PARENTHETICAL,
                content="(wiping mascara)",
            ),
            ASTElement(
                node_type=ASTNodeType.DIALOGUE,
                content="He dumped me over GroupMe, Kelly.",
            ),
            ASTElement(
                node_type=ASTNodeType.TRANSITION,
                content="CUT TO:",
            ),
        ]

        paras = self.compiler._normalize_ast_to_paragraphs(sample_ast)
        self.assertEqual(len(paras), 6)
        self.assertEqual(paras[0], ("INT. THE BUTTON NIGHTCLUB - NIGHT", "SceneHeading"))
        self.assertEqual(paras[1], ("Cigarette smoke swirls under purple neon.", "Action"))
        self.assertEqual(paras[2], ("FRANCINE LING", "CharacterCue"))
        self.assertEqual(paras[3], ("(wiping mascara)", "Parenthetical"))
        self.assertEqual(paras[4], ("He dumped me over GroupMe, Kelly.", "Dialogue"))
        self.assertEqual(paras[5], ("CUT TO:", "Transition"))

    def test_paragraph_and_char_invariants(self):
        """Verify Rust engine invariants: paras == newline + 1, char run len == byte length."""
        sample_text = (
            "INT. TEST ROOM - DAY\n\n"
            "A writer stares at the terminal.\n\n"
            "WRITER\n"
            "(smiling)\n"
            "It compiles.\n\n"
            "FADE OUT."
        )
        ast = FountainParser.parse(sample_text)
        paragraphs = self.compiler._normalize_ast_to_paragraphs(ast)
        doc = self.compiler._build_document(paragraphs, page_count=2, title="Test Script")

        main_story = doc.stories["20"]
        expected_paras = main_story.text.count("\n") + 1
        self.assertEqual(len(main_story.paras), expected_paras)

        total_char_len = sum(c.len for c in main_story.chars)
        self.assertEqual(total_char_len, len(main_story.text.encode("utf-8")))

    def test_orphan_prevention_rules(self):
        """Verify keepWithNext rules are applied to prevent dangling cues and scene headings."""
        ast = [
            ASTElement(node_type=ASTNodeType.SCENE_HEADING, content="INT. ROOM - DAY"),
            ASTElement(node_type=ASTNodeType.CHARACTER, content="RAINEE"),
            ASTElement(node_type=ASTNodeType.DIALOGUE, content="Hello darling."),
        ]
        paragraphs = self.compiler._normalize_ast_to_paragraphs(ast)
        doc = self.compiler._build_document(paragraphs, page_count=1, title="Keeps Test")

        styles = {s["name"]: s for s in doc.styles["paragraph"]}
        self.assertEqual(styles["SceneHeading"]["para"]["keepWithNext"], 1)
        self.assertEqual(styles["CharacterCue"]["para"]["keepWithNext"], 1)

    def test_compile_package_and_preflight(self):
        """Verify package assembly and headless preflight check with designcraft-cli."""
        sample_script = (
            "EXT. CHERRY STREET - AFTERNOON\n\n"
            "A golden fox tail swishes lazily from the porch railing.\n\n"
            "RAINEE\n"
            "(sipping chilled Junmai Ginjo)\n"
            "Furniture loyalty is a virtue, Francine.\n\n"
            "FRANCINE LING\n"
            "You broke the mahogany loveseat, Rainee!\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_pkg = Path(tmpdir) / "test_script.designcraft"
            self.compiler.compile_text(sample_script, out_pkg, title="Test Rainee Scene")

            self.assertTrue(out_pkg.exists())

            # Check zip archive structure
            with zipfile.ZipFile(out_pkg, "r") as z:
                namelist = z.namelist()
                self.assertIn("mimetype", namelist)
                self.assertIn("meta.json", namelist)
                self.assertIn("document.json", namelist)

                # Check mimetype is uncompressed
                info = z.getinfo("mimetype")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

                # Check document parses
                doc_data = json.loads(z.read("document.json"))
                self.assertEqual(doc_data["title"], "Test Rainee Scene")

            # Preflight verification via CLI
            if self.compiler.cli_path.exists():
                res = subprocess.run(
                    [
                        str(self.compiler.cli_path),
                        "run",
                        "--in",
                        str(out_pkg),
                        "--cmd",
                        "preflight.run",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(res.returncode, 0)
                report = json.loads(res.stdout)
                self.assertEqual(report["errors"], 0)
                self.assertEqual(report["warnings"], 0)

    def test_pdf_export(self):
        """Verify high-speed headless compilation to PDF."""
        if not self.compiler.cli_path.exists():
            self.skipTest("designcraft-cli binary not found")

        sample_script = (
            "INT. KIMONO LIVING ROOM - DUSK\n\n"
            "Rainee lounges across the custom-reinforced cedar futon.\n\n"
            "STELLA\n"
            "Check the drop, Mom. 800 GSM French terry hoodie.\n\n"
            "RAINEE\n"
            "(grinning)\n"
            "Stellar posture, little sister.\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_pkg = Path(tmpdir) / "test_pdf.designcraft"
            self.compiler.compile_text(sample_script, out_pkg, title="Test PDF")

            out_pdf = self.compiler.export_pdf(out_pkg)
            self.assertTrue(out_pdf.exists())
            self.assertGreater(out_pdf.stat().st_size, 5000)

            # Verify PDF magic bytes
            with open(out_pdf, "rb") as f:
                header = f.read(4)
                self.assertEqual(header, b"%PDF")


if __name__ == "__main__":
    unittest.main()
