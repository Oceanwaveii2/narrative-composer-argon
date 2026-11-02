"""
Unit and Integration Tests for DesignCraft CLI Runner and Subprocess Pipeline.
Verifies multi-format export (PDF, IDML, PNG), preflight audits, font queries, and font packaging.
"""

from pathlib import Path
import tempfile
import unittest
import zipfile

from narrative_composer.designcraft import DesignCraftCompiler, DesignCraftCLI


@unittest.skip("DesignCraft disabled")
class TestDesignCraftCLI(unittest.TestCase):
    def setUp(self):
        try:
            self.compiler = DesignCraftCompiler()
            self.cli = DesignCraftCLI()
        except FileNotFoundError:
            self.skipTest("DesignCraft CLI binary not found in workspace")

    def test_cli_runner_initialization(self):
        """Verify binary path discovery and execution check."""
        self.assertTrue(self.cli.cli_path.exists())
        res = self.cli.run_raw(["--version"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("designcraft-cli", res.stdout)

    def test_preflight_and_font_list(self):
        """Verify preflight audit and font listing on master screenplay."""
        master_pkg = (
            Path(__file__).resolve().parent.parent.parent
            / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.designcraft"
        )
        if not master_pkg.exists():
            self.skipTest("HOT_SCOOMP_COMPLETE_CHRONOLOGY.designcraft not generated yet")

        # 1. Preflight
        report = self.cli.preflight(master_pkg)
        self.assertEqual(report.get("errors"), 0)
        self.assertEqual(report.get("warnings"), 0)
        self.assertEqual(len(report.get("issues", [])), 0)

        # 2. Font listing
        fonts = self.cli.list_fonts(master_pkg)
        self.assertGreater(len(fonts), 0)
        for font in fonts:
            self.assertEqual(font.get("family"), "Courier New")
            self.assertFalse(font.get("missing"))
            self.assertEqual(font.get("matchStatus"), "exact")

    def test_export_pdf_and_idml(self):
        """Verify export to PDF and Adobe InDesign (.idml) package."""
        sample_script = (
            "INT. SCREENPLAY LAB - DAY\n\n"
            "WRITER\n"
            "Testing InDesign export bridge.\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_path = Path(tmpdir) / "test_export.designcraft"
            self.compiler.compile_text(sample_script, pkg_path, title="Export Test")

            # 1. PDF Export
            out_pdf = self.cli.export_pdf(pkg_path)
            self.assertTrue(out_pdf.exists())
            self.assertGreater(out_pdf.stat().st_size, 3000)
            with open(out_pdf, "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")

            # 2. IDML Export
            out_idml = self.cli.export_idml(pkg_path)
            self.assertTrue(out_idml.exists())
            self.assertGreater(out_idml.stat().st_size, 5000)

            # Check IDML internal structure
            with zipfile.ZipFile(out_idml, "r") as z:
                names = z.namelist()
                self.assertIn("mimetype", names)
                self.assertIn("designmap.xml", names)
                self.assertIn("Resources/Styles.xml", names)

    def test_export_png_page(self):
        """Verify rendering specific page to PNG image."""
        sample_script = (
            "INT. ART STUDIO - NIGHT\n\n"
            "A neon canvas glows warmly on the easel.\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_path = Path(tmpdir) / "test_render.designcraft"
            self.compiler.compile_text(sample_script, pkg_path, title="Render Test")

            out_png = self.cli.export_png(pkg_path, page=1, scale=1.0)
            self.assertTrue(out_png.exists())
            self.assertGreater(out_png.stat().st_size, 5000)
            with open(out_png, "rb") as f:
                header = f.read(8)
                self.assertEqual(header, b"\x89PNG\r\n\x1a\n")

    def test_package_document_fonts(self):
        """Verify Document Fonts packaging helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_fonts = self.cli.package_document_fonts(tmpdir)
            self.assertTrue(doc_fonts.exists())
            cour_file = doc_fonts / "cour.ttf"
            if cour_file.exists():
                self.assertGreater(cour_file.stat().st_size, 100000)


if __name__ == "__main__":
    unittest.main()
