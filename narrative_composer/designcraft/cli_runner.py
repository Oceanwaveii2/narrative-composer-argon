"""
DesignCraft CLI Runner & Subprocess Automation Bridge.
Orchestrates headless compilation, preflight validation, multi-format export (PDF, IDML, EPUB, PNG),
and font packaging for the DesignCraft publishing engine.
"""

from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Union


class DesignCraftCLI:
    """
    Subprocess adapter for designcraft-cli.exe.
    Provides typed methods for headless document operations, audits, and exports.
    """

    def __init__(self, cli_path: Optional[Union[str, Path]] = None):
        if cli_path:
            self.cli_path = Path(cli_path)
        else:
            root = Path(__file__).resolve().parent.parent.parent
            self.cli_path = (
                root
                / "designcraft_src"
                / "target"
                / "release"
                / "designcraft-cli.exe"
            )

        if not self.cli_path.exists():
            raise FileNotFoundError(
                f"DesignCraft CLI binary not found at: {self.cli_path}"
            )

    def run_raw(self, args: List[str]) -> subprocess.CompletedProcess[str]:
        """Runs the CLI binary with raw argument list."""
        cmd = [str(self.cli_path)] + args
        return subprocess.run(cmd, capture_output=True, text=True)

    def run_command(
        self,
        in_path: Union[str, Path],
        cmd_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a DesignCraft internal command (`--cmd name=json`) against a document.
        """
        in_p = Path(in_path)
        if params is not None:
            cmd_arg = f"{cmd_name}={json.dumps(params)}"
        else:
            cmd_arg = cmd_name

        res = self.run_raw(["run", "--in", str(in_p), "--cmd", cmd_arg])
        if res.returncode != 0:
            raise RuntimeError(
                f"DesignCraft command '{cmd_name}' failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )

        stdout = res.stdout.strip()
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"raw_output": stdout}
        return {}

    def export_pdf(
        self,
        in_path: Union[str, Path],
        out_path: Optional[Union[str, Path]] = None,
        scale: float = 1.0,
    ) -> Path:
        """Exports a .designcraft package to PDF."""
        in_p = Path(in_path)
        out_p = Path(out_path) if out_path else in_p.with_suffix(".pdf")

        args = ["run", "--in", str(in_p)]
        if scale != 1.0:
            args.extend(["--scale", str(scale)])
        args.extend(["--export", str(out_p)])

        res = self.run_raw(args)
        if res.returncode != 0:
            raise RuntimeError(
                f"PDF export failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )
        return out_p

    def export_idml(
        self,
        in_path: Union[str, Path],
        out_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Exports a .designcraft package to Adobe InDesign Interchange (.idml)."""
        in_p = Path(in_path)
        out_p = Path(out_path) if out_path else in_p.with_suffix(".idml")

        res_data = self.run_command(
            in_path=in_p,
            cmd_name="file.exportIdml",
            params={"path": str(out_p.resolve())},
        )
        if not out_p.exists():
            raise RuntimeError(f"IDML export did not produce expected file: {out_p}")
        return out_p

    def export_png(
        self,
        in_path: Union[str, Path],
        out_path: Optional[Union[str, Path]] = None,
        page: int = 1,
        scale: float = 1.5,
    ) -> Path:
        """
        Renders a specific page (1-indexed) to a high-resolution PNG image.
        Note: designcraft-cli --page is 0-indexed.
        """
        in_p = Path(in_path)
        out_p = Path(out_path) if out_path else in_p.with_suffix(f".page_{page}.png")

        page_zero_indexed = max(0, page - 1)
        args = [
            "run",
            "--in",
            str(in_p),
            "--page",
            str(page_zero_indexed),
            "--scale",
            str(scale),
            "--export",
            str(out_p),
        ]

        res = self.run_raw(args)
        if res.returncode != 0:
            raise RuntimeError(
                f"PNG export for page {page} failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )
        return out_p

    def export_all_pages(
        self,
        in_path: Union[str, Path],
        out_dir: Union[str, Path],
        scale: float = 1.0,
    ) -> List[Path]:
        """Renders every page of the document into PNG images in out_dir."""
        in_p = Path(in_path)
        out_d = Path(out_dir)
        out_d.mkdir(parents=True, exist_ok=True)

        args = [
            "run",
            "--in",
            str(in_p),
            "--scale",
            str(scale),
            "--all-pages",
            str(out_d),
        ]

        res = self.run_raw(args)
        if res.returncode != 0:
            raise RuntimeError(
                f"All-pages PNG export failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )

        return sorted(list(out_d.glob("*.png")))

    def export_epub(
        self,
        in_path: Union[str, Path],
        out_path: Optional[Union[str, Path]] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Path:
        """Exports the document to EPUB format."""
        in_p = Path(in_path)
        out_p = Path(out_path) if out_path else in_p.with_suffix(".epub")

        params: Dict[str, Any] = {"path": str(out_p.resolve())}
        if title:
            params["title"] = title
        if author:
            params["author"] = author

        self.run_command(in_path=in_p, cmd_name="file.exportEpub", params=params)
        if not out_p.exists():
            raise RuntimeError(f"EPUB export did not produce expected file: {out_p}")
        return out_p

    def preflight(self, in_path: Union[str, Path]) -> Dict[str, Any]:
        """Runs preflight document analysis and returns issues report."""
        return self.run_command(in_path=in_path, cmd_name="preflight.run")

    def list_fonts(self, in_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """Lists all fonts referenced in document with matching and missing status."""
        res = self.run_command(in_path=in_path, cmd_name="font.list")
        if isinstance(res, list):
            return res
        return []

    def replace_font(
        self,
        in_path: Union[str, Path],
        from_family: str,
        to_family: str,
        redefine_styles: bool = True,
    ) -> Dict[str, Any]:
        """Finds and replaces a font across text and paragraph styles."""
        return self.run_command(
            in_path=in_path,
            cmd_name="font.replace",
            params={
                "family": from_family,
                "toFamily": to_family,
                "redefineStyles": redefine_styles,
            },
        )

    @staticmethod
    def package_document_fonts(target_dir: Union[str, Path]) -> Path:
        """
        Creates a 'Document Fonts' folder beside target documents and copies
        monospaced font assets so DesignCraft/InDesign load fonts without missing glyphs.
        """
        dest_dir = Path(target_dir) / "Document Fonts"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Standard Windows fonts directory
        win_fonts = Path(r"C:\Windows\Fonts")
        font_files = [
            "cour.ttf",
            "courbd.ttf",
            "couri.ttf",
            "courbi.ttf",
        ]

        copied = 0
        for f_name in font_files:
            src = win_fonts / f_name
            dst = dest_dir / f_name
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                copied += 1

        return dest_dir
