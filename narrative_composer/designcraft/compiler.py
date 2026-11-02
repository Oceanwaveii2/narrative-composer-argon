"""
DesignCraft Screenplay Compiler Engine.
Translates Fountain/Markdown screenplay AST into native, validated DesignCraft documents (.designcraft)
and orchestrates high-speed headless compilation to PDF via designcraft-cli.
"""

from __future__ import annotations
import json
from math import ceil
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union
import zipfile

from ..models.ast_nodes import ASTElement, ASTNodeType
from ..parser.fountain_lexer import FountainParser
from .models import (
    CharRun,
    Columns,
    DesignCraftDoc,
    Item,
    ItemContent,
    Layer,
    Margins,
    Page,
    ParaFormat,
    PathData,
    Spread,
    Story,
    Subpath,
    SubpathAnchor,
    TextFrameOptions,
    default_corners,
    default_effects,
)
from .themes import ThemeConfig, get_theme, ARCHIVAL_WARM_IVORY


class DesignCraftCompiler:
    """
    AST-to-DesignCraft Screenplay Compiler.
    Enforces all DesignCraft Rust engine typography invariants and provides
    calibrated multi-page autoflow with running headers and orphan prevention.
    """

    NODE_STYLE_MAP = {
        ASTNodeType.SCENE_HEADING: "SceneHeading",
        ASTNodeType.ACTION: "Action",
        ASTNodeType.CHARACTER: "CharacterCue",
        ASTNodeType.PARENTHETICAL: "Parenthetical",
        ASTNodeType.DIALOGUE: "Dialogue",
        ASTNodeType.TRANSITION: "Transition",
    }

    def __init__(
        self,
        preset_path: Optional[Path] = None,
        font_family: str = "Courier New",
        cli_path: Optional[Path] = None,
        theme: Union[str, ThemeConfig] = "archival_ivory",
    ):
        self.root = Path(__file__).resolve().parent.parent.parent
        self.preset_path = preset_path or (
            self.root / "designcraft_bridge" / "schemas" / "screenplay_preset.json"
        )
        self.font_family = font_family
        self.theme: ThemeConfig = get_theme(theme) if isinstance(theme, str) else theme
        self.cli_path = cli_path or (
            self.root / "designcraft_src" / "target" / "release" / "designcraft-cli.exe"
        )

        # Load preset configuration
        if self.preset_path.exists():
            self.preset = json.loads(self.preset_path.read_text(encoding="utf-8"))
        else:
            self.preset = self._get_fallback_preset()

        # Load sample components for swatches, effects, and object styles
        self._load_baseline_assets()

    def _get_fallback_preset(self) -> Dict[str, Any]:
        return {
            "pageWidth": 612.0,
            "pageHeight": 792.0,
            "baselineGrid": {
                "start": 72.0,
                "increment": 12.0,
                "relativeTo": "topMargin",
                "color": [140, 205, 230],
                "viewThreshold": 0.75,
            },
            "styles": {},
        }

    def _load_baseline_assets(self) -> None:
        sample_path = self.root / "sample.designcraft"
        if sample_path.exists():
            with zipfile.ZipFile(sample_path, "r") as z:
                doc = json.loads(z.read("document.json"))
                self.object_styles = doc.get("styles", {}).get("object", [])
                self.text_variables = doc.get("textVariables", [])
                self.footnote_options = doc.get("footnoteOptions", {})
                self.endnote_options = doc.get("endnoteOptions", {})
                self.xref_formats = doc.get("xrefFormats", [])
        else:
            self.object_styles = [
                {"name": "[Basic Text Frame]", "basedOn": None},
                {"name": "[Basic Graphics Frame]", "basedOn": None},
            ]
            self.text_variables = []
            self.footnote_options = {}
            self.endnote_options = {}
            self.xref_formats = []

        # Calibrated CMYK Process Swatches conforming to print intent (0 preflight warnings)
        base_swatches = [
            {
                "name": "[None]",
                "value": {"kind": "none"},
                "locked": True,
                "named": True,
                "hidden": False,
            },
            {
                "name": "[Registration]",
                "value": {"kind": "registration"},
                "locked": True,
                "named": True,
                "hidden": False,
            },
            {
                "name": "[Paper]",
                "value": {
                    "kind": "paper",
                    "color": {"model": "rgb", "r": 1.0, "g": 1.0, "b": 1.0},
                },
                "locked": True,
                "named": True,
                "hidden": False,
            },
            {
                "name": "[Black]",
                "value": {
                    "kind": "color",
                    "color": {"model": "cmyk", "c": 0.0, "m": 0.0, "y": 0.0, "k": 1.0},
                    "color_type": "process",
                },
                "locked": True,
                "named": True,
                "hidden": False,
            },
        ]
        swatch_map = {s["name"]: s for s in base_swatches}
        for s_def in self.theme.swatches:
            swatch_map[s_def.name] = s_def.to_designcraft()
        self.swatches = list(swatch_map.values())

    def compile_file(
        self,
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        title: Optional[str] = None,
        theme: Optional[Union[str, ThemeConfig]] = None,
    ) -> Path:
        """Parses a screenplay file (.md or .fountain) and compiles it into a .designcraft package."""
        p = Path(input_path)
        content = p.read_text(encoding="utf-8")
        doc_title = title or p.stem.replace("_", " ").title()
        out_p = Path(output_path) if output_path else p.with_suffix(".designcraft")
        ast = FountainParser.parse(content)
        return self.compile_ast(ast, output_path=out_p, title=doc_title, theme=theme)

    def compile_text(
        self,
        script_text: str,
        output_path: Union[str, Path],
        title: str = "Screenplay",
        theme: Optional[Union[str, ThemeConfig]] = None,
    ) -> Path:
        """Parses a screenplay raw text string and compiles it into a .designcraft package."""
        ast = FountainParser.parse(script_text)
        return self.compile_ast(ast, output_path=output_path, title=title, theme=theme)

    def compile_ast(
        self,
        ast: List[ASTElement],
        output_path: Union[str, Path],
        title: str = "Screenplay",
        theme: Optional[Union[str, ThemeConfig]] = None,
    ) -> Path:
        """
        Translates a list of ASTElement nodes into a calibrated multi-page DesignCraft document.
        """
        if theme is not None:
            self.theme = get_theme(theme) if isinstance(theme, str) else theme
            self._load_baseline_assets()
        out_p = Path(output_path)
        paragraphs = self._normalize_ast_to_paragraphs(ast)
        if not paragraphs:
            paragraphs = [("FADE IN:", "Transition")]

        # 1. Estimate initial page count
        estimated_pages = self._estimate_page_count(paragraphs)

        # 2. Build document with estimated page count
        doc = self._build_document(paragraphs, estimated_pages, title)

        # 3. Write intermediate package
        self._write_package(doc, out_p)

        # 4. Calibrate autoflow using preflight if CLI is available
        if self.cli_path.exists():
            final_pages = self._calibrate_autoflow(paragraphs, estimated_pages, title, out_p)
            if final_pages != estimated_pages:
                doc = self._build_document(paragraphs, final_pages, title)
                self._write_package(doc, out_p)

        return out_p

    def _normalize_ast_to_paragraphs(
        self, ast: List[ASTElement]
    ) -> List[Tuple[str, str]]:
        """
        Extracts paragraphs and styles, handling multi-line elements and stripping CR.
        """
        paragraphs: List[Tuple[str, str]] = []
        for element in ast:
            style_name = self.NODE_STYLE_MAP.get(element.node_type, "Action")
            clean_text = element.content.replace("\r", "")
            for line in clean_text.split("\n"):
                line = line.strip()
                if line:
                    paragraphs.append((line, style_name))
        return paragraphs

    def _estimate_page_count(self, paragraphs: List[Tuple[str, str]]) -> int:
        """
        Calculates line budgets to estimate total pages needed.
        US Letter 12pt line pitch gives 54 lines/page.
        """
        total_lines = 0
        for text, style in paragraphs:
            if style == "SceneHeading":
                total_lines += 3
            elif style == "Action":
                total_lines += max(1, ceil(len(text) / 60)) + 1
            elif style == "CharacterCue":
                total_lines += 2
            elif style == "Parenthetical":
                total_lines += 1
            elif style == "Dialogue":
                total_lines += max(1, ceil(len(text) / 35)) + 1
            elif style == "Transition":
                total_lines += 3
            else:
                total_lines += 2

        # Safe line budget per page (accounting for paragraph margins)
        lines_per_page = 48
        return max(1, ceil(total_lines / lines_per_page))

    def _build_document(
        self,
        paragraphs: List[Tuple[str, str]],
        page_count: int,
        title: str,
    ) -> DesignCraftDoc:
        """
        Assembles the complete DesignCraft document data structure.
        """
        page_width = float(self.preset.get("pageWidth", 612.0))
        page_height = float(self.preset.get("pageHeight", 792.0))

        # Main story text and formats
        story_text = "\n".join(p[0] for p in paragraphs)
        story_paras = [ParaFormat(style=p[1]) for p in paragraphs]
        story_chars = [
            CharRun(len=len(story_text.encode("utf-8")), style="[None]")
        ]

        # Invariant Verification
        expected_para_count = story_text.count("\n") + 1
        if len(story_paras) != expected_para_count:
            raise ValueError(
                f"Paragraph invariant violated: {len(story_paras)} formats for {expected_para_count} paragraphs"
            )

        spreads: List[Spread] = []
        main_frames: List[int] = []
        stories: Dict[str, Story] = {}

        for p_idx in range(1, page_count + 1):
            frame_id = 100 + p_idx
            main_frames.append(frame_id)

            items = []

            # Full bleed background rectangle if enabled by theme
            if self.theme.enable_background:
                bg_item_id = 5000 + p_idx
                bleed_item = Item(
                    id=bg_item_id,
                    name="Page Background",
                    layer=1,
                    shape="rectangle",
                    path=PathData(
                        subpaths=[
                            Subpath(
                                anchors=[
                                    SubpathAnchor(p=[-9.0, -9.0]),
                                    SubpathAnchor(p=[page_width + 9.0, -9.0]),
                                    SubpathAnchor(p=[page_width + 9.0, page_height + 9.0]),
                                    SubpathAnchor(p=[-9.0, page_height + 9.0]),
                                ],
                                closed=True,
                            )
                        ]
                    ),
                    fill={
                        "kind": "color",
                        "swatch": self.theme.bg_swatch,
                        "tint": 1.0,
                        "overprint": False,
                    },
                    stroke={"kind": "none"},
                    corners=default_corners(),
                    opacity=1.0,
                    blend="Normal",
                    effects=default_effects(),
                    wrap={"mode": "none"},
                    locked=False,
                    hidden=False,
                    nonprinting=False,
                    object_style="[Basic Graphics Frame]",
                    content=ItemContent(type="unassigned"),
                )
                items.append(bleed_item)

            # Printable text frame rect: left 108.0, top 72.0, right 540.0, bottom 720.0
            main_frame_item = Item(
                id=frame_id,
                layer=1,
                shape="rectangle",
                path=PathData(
                    subpaths=[
                        Subpath(
                            anchors=[
                                SubpathAnchor(p=[108.0, 72.0]),
                                SubpathAnchor(p=[540.0, 72.0]),
                                SubpathAnchor(p=[540.0, 720.0]),
                                SubpathAnchor(p=[108.0, 720.0]),
                            ],
                            closed=True,
                        )
                    ]
                ),
                content=ItemContent(
                    type="text",
                    story=20,
                    options=TextFrameOptions(),
                ),
            )
            items.append(main_frame_item)

            # Running Page Header on Page 2+ (e.g. "2.")
            if p_idx >= 2:
                hdr_item_id = 200 + p_idx
                hdr_story_id = 300 + p_idx

                hdr_frame_item = Item(
                    id=hdr_item_id,
                    layer=1,
                    shape="rectangle",
                    path=PathData(
                        subpaths=[
                            Subpath(
                                anchors=[
                                    SubpathAnchor(p=[468.0, 36.0]),
                                    SubpathAnchor(p=[540.0, 36.0]),
                                    SubpathAnchor(p=[540.0, 54.0]),
                                    SubpathAnchor(p=[468.0, 54.0]),
                                ],
                                closed=True,
                            )
                        ]
                    ),
                    content=ItemContent(
                        type="text",
                        story=hdr_story_id,
                        options=TextFrameOptions(),
                    ),
                )
                items.append(hdr_frame_item)

                hdr_str = f"{p_idx}."
                stories[str(hdr_story_id)] = Story(
                    id=hdr_story_id,
                    text=hdr_str,
                    paras=[ParaFormat(style="PageHeader")],
                    chars=[
                        CharRun(
                            len=len(hdr_str.encode("utf-8")),
                            style="[None]",
                        )
                    ],
                    frames=[hdr_item_id],
                )

            # Build spread and page
            spread = Spread(
                id=p_idx,
                pages=[
                    Page(
                        id=p_idx * 10,
                        width=page_width,
                        height=page_height,
                        x=0.0,
                        side="single",
                        margins=Margins(
                            top=72.0, bottom=72.0, inside=108.0, outside=72.0
                        ),
                        columns=Columns(count=1, gutter=0.0),
                        show_parent_items=True,
                    )
                ],
                items=items,
                allow_shuffle=True,
            )
            spreads.append(spread)

        # Assign main story 20
        stories["20"] = Story(
            id=20,
            text=story_text,
            paras=story_paras,
            chars=story_chars,
            frames=main_frames,
        )

        # Construct Typography Styles
        styles_para = [
            {
                "name": "[No Paragraph Style]",
                "basedOn": None,
                "chars": {},
                "para": {},
            },
            {
                "name": "[Basic Paragraph]",
                "basedOn": None,
                "chars": {
                    "fontFamily": self.font_family,
                    "size": 12.0,
                    "leading": {"kind": "points", "value": 12.0},
                    "fill": "[Black]",
                },
                "para": {},
            },
        ]

        preset_styles = self.preset.get("styles", {})
        style_keys = [
            "SceneHeading",
            "Action",
            "CharacterCue",
            "Parenthetical",
            "Dialogue",
            "Transition",
            "PageHeader",
        ]
        for k in style_keys:
            st = json.loads(
                json.dumps(
                    preset_styles.get(
                        k,
                        {
                            "name": k,
                            "basedOn": "[Basic Paragraph]",
                            "chars": {
                                "size": 12.0,
                                "leading": {"kind": "points", "value": 12.0},
                            },
                            "para": {},
                        },
                    )
                )
            )
            st["chars"]["fontFamily"] = self.font_family

            # Apply theme overrides for colors, rules, tracking, and leading
            if k in self.theme.style_overrides:
                override = self.theme.style_overrides[k]
                if "chars" in override:
                    st.setdefault("chars", {}).update(override["chars"])
                if "para" in override:
                    st.setdefault("para", {}).update(override["para"])

            # Enforce orphan prevention rules: keep with next line
            if k in ["SceneHeading", "CharacterCue", "Parenthetical", "Transition"]:
                st.setdefault("para", {})["keepWithNext"] = 1

            styles_para.append(st)

        doc_dict = {
            "title": title,
            "settings": {
                "intent": "print",
                "pageWidth": page_width,
                "pageHeight": page_height,
                "facingPages": False,
                "primaryTextFrame": True,
                "bleed": [9.0, 9.0, 9.0, 9.0] if self.theme.enable_background else [0.0, 0.0, 0.0, 0.0],
                "slug": [0.0, 0.0, 0.0, 0.0],
                "horizontalUnits": "points",
                "verticalUnits": "points",
                "baselineGrid": self.preset.get(
                    "baselineGrid",
                    {
                        "start": 72.0,
                        "increment": 12.0,
                        "relativeTo": "topMargin",
                        "color": [140, 205, 230],
                        "viewThreshold": 0.75,
                    },
                ),
                "grid": {
                    "horizontal": 72.0,
                    "vertical": 72.0,
                    "subdivisions": 8,
                    "color": [200, 200, 200],
                    "inBack": True,
                },
                "pasteboard": [72.0, 72.0],
                "marginColor": [255, 56, 255],
                "columnColor": [166, 40, 255],
                "bleedColor": [255, 72, 103],
                "slugColor": [100, 188, 221],
                "keyboardIncrement": 1.0,
                "kerningIncrement": 20.0,
                "chapterNumber": 1,
                "chapterStyle": "arabic",
                "chapterSource": "automatic",
                "globalLight": 120.0,
                "advancedType": {
                    "superscriptSize": 58.3,
                    "superscriptPosition": 33.3,
                    "subscriptSize": 58.3,
                    "subscriptPosition": 33.3,
                },
                "blendSpace": "cmyk",
                "overprintBlack": True,
                "trackChanges": False,
                "glyphFallback": True,
                "rulerOrigin": "spread",
                "newObject": {
                    "fill": "[None]",
                    "fillTint": 1.0,
                    "stroke": "[Black]",
                    "strokeTint": 1.0,
                },
            },
            "spreads": spreads,
            "parents": [],
            "layers": [Layer()],
            "stories": stories,
            "styles": {
                "paragraph": styles_para,
                "character": [{"name": "[None]", "basedOn": None, "chars": {}}],
                "object": self.object_styles,
                "cell": [],
                "table": [],
                "defaultParagraph": "Action",
                "defaultCharacter": "[None]",
                "defaultTextFrame": "[Basic Text Frame]",
                "defaultGraphicFrame": "[Basic Graphics Frame]",
            },
            "swatches": self.swatches,
            "endnoteOptions": self.endnote_options,
            "sections": [
                {
                    "start": 0,
                    "startNumber": 1,
                    "style": "arabic",
                    "prefix": "",
                    "marker": "",
                    "includePrefix": False,
                }
            ],
            "assets": {},
            "textVariables": self.text_variables,
            "footnoteOptions": self.footnote_options,
            "xrefFormats": self.xref_formats,
            "created": 1700000000,
            "modified": 1700000000,
            "nextId": max(10000, 6000 + page_count * 20),
        }

        return DesignCraftDoc(**doc_dict)

    def _write_package(self, doc: DesignCraftDoc, package_path: Path) -> None:
        """Writes the document into the .designcraft zip archive."""
        package_path.parent.mkdir(parents=True, exist_ok=True)
        doc_json = doc.model_dump(by_alias=True, mode="json")

        with zipfile.ZipFile(package_path, "w") as z:
            # 1. mimetype (stored uncompressed)
            z.writestr(
                "mimetype",
                b"application/vnd.designcraft+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            # 2. meta.json
            meta = {
                "format": "designcraft",
                "version": 2,
                "generator": "DesignCraft 0.8.0",
            }
            z.writestr(
                "meta.json",
                json.dumps(meta),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            # 3. document.json
            z.writestr(
                "document.json",
                json.dumps(doc_json, indent=2),
                compress_type=zipfile.ZIP_DEFLATED,
            )

    def _calibrate_autoflow(
        self,
        paragraphs: List[Tuple[str, str]],
        initial_pages: int,
        title: str,
        package_path: Path,
        max_attempts: int = 10,
    ) -> int:
        """
        Runs preflight to detect overset and trims empty trailing pages, calibrating exact page count.
        """
        pages = initial_pages
        # 1. Expand if overset
        for _ in range(max_attempts):
            res = subprocess.run(
                [
                    str(self.cli_path),
                    "run",
                    "--in",
                    str(package_path),
                    "--cmd",
                    "preflight.run",
                ],
                capture_output=True,
                text=True,
            )

            if res.returncode != 0:
                break

            try:
                report = json.loads(res.stdout)
                issues = report.get("issues", [])
                overset_issues = [i for i in issues if i.get("kind") == "overset"]

                if not overset_issues:
                    break

                # Overset found: calculate additional pages needed
                extra_pages = 1
                for issue in overset_issues:
                    msg = issue.get("message", "")
                    words = msg.split()
                    if len(words) >= 3 and words[2].isdigit():
                        chars = int(words[2])
                        extra_pages = max(extra_pages, ceil(chars / 1400))

                pages += extra_pages
                doc = self._build_document(paragraphs, pages, title)
                self._write_package(doc, package_path)

            except Exception:
                break

        # 2. Trim trailing empty pages if pypdf is available
        try:
            import pypdf
            temp_pdf = package_path.with_suffix(".temp.pdf")
            self.export_pdf(package_path, temp_pdf)
            reader = pypdf.PdfReader(str(temp_pdf))
            last_body_page = 1
            for idx, p in enumerate(reader.pages):
                txt = p.extract_text().strip()
                # Running headers alone are typically <= 6 characters (e.g. '60.')
                if len(txt) > 6:
                    last_body_page = idx + 1
            temp_pdf.unlink(missing_ok=True)

            if last_body_page < pages:
                pages = last_body_page
                doc = self._build_document(paragraphs, pages, title)
                self._write_package(doc, package_path)
        except Exception:
            pass

        return pages

    def export_pdf(
        self,
        package_path: Union[str, Path],
        pdf_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Compiles the .designcraft file to PDF via designcraft-cli.
        """
        in_p = Path(package_path)
        out_p = Path(pdf_path) if pdf_path else in_p.with_suffix(".pdf")

        if not self.cli_path.exists():
            raise FileNotFoundError(
                f"DesignCraft CLI binary not found at: {self.cli_path}"
            )

        cmd = [
            str(self.cli_path),
            "run",
            "--in",
            str(in_p),
            "--export",
            str(out_p),
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"DesignCraft PDF export failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )

        return out_p
