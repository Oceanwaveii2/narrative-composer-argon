"""
Reader renderer: projects a Document into the standalone, self-contained reader HTML.

Rendering is a pure function of the document plus a theme. Presentation chrome
(title card, navigation labels, footer) lives in the theme rather than in the emitter,
so the same renderer formats any screenplay that has a Document.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from narrative_composer.compiler.document import (
    BlockRole,
    Document,
    NavSection,
    build_nav_sections,
)
from narrative_composer.compiler.presentation import get_character_transformation_pill

TAILWIND_ASSET = Path(__file__).resolve().parent / "assets" / "tailwind.js"
DEFAULT_TAILWIND_CDN = "https://cdn.tailwindcss.com"


@lru_cache(maxsize=1)
def _vendored_tailwind() -> Optional[str]:
    """Returns the locally vendored Tailwind runtime, or None if it is absent."""
    try:
        source = TAILWIND_ASSET.read_text(encoding="utf-8")
    except OSError:
        return None
    # The runtime is inlined inside a <script> element; guard the terminator defensively.
    return source.replace("</script", "<\\/script")


@dataclass(frozen=True)
class ReaderTheme:
    """All presentation strings for the reader shell."""

    page_title: str
    brand_badge: str
    brand_title: str
    verified_note: str
    graph_href: str
    hero_h1_html: str
    hero_paragraph: str
    canon_heading: str
    canon_rows: Sequence[str]
    index_heading: str
    footer_title: str
    footer_line: str
    nav_group_names: Sequence[str]
    nav_group_prefixes: Sequence[str]
    act_keywords: Sequence[Tuple[str, int]] = field(default_factory=tuple)
    chunk_keywords: Sequence[Tuple[str, int]] = field(default_factory=tuple)
    label_replacements: Sequence[Tuple[str, str]] = field(default_factory=tuple)
    # None = inline the vendored Tailwind runtime (fully offline, self-contained).
    # Set to a URL to load Tailwind from a CDN instead.
    tailwind_cdn: Optional[str] = None
    # None = rely on the local font stack ('Courier Prime' if installed, else Courier
    # New / system-ui). Set to a Google Fonts URL to load webfonts instead.
    fonts_import_url: Optional[str] = None
    compact: bool = False


HOT_SCOOMP_THEME = ReaderTheme(
    page_title="Hot Scoomp — Unabridged Master Chronology (Episode 0 to Finale)",
    brand_badge="HOT SCOOMP",
    brand_title="Unabridged Master Reader",
    verified_note="✓ Verified Master Screenplay",
    graph_href="out/graphs/master.viewer.html",
    hero_h1_html='HOT SCOOMP <span class="text-amber-400">:</span> COMPLETE CHRONOLOGY',
    hero_paragraph=(
        "The unabridged full arc: Episode 0 (Origin), Ep 16 (Spring Breakup AU), "
        "The Prequel (Cult, Congo &amp; Transformations), Acts 1 &amp; 2 (Steven Transformation), "
        "and The Climax Tag."
    ),
    canon_heading="CANON INTEGRITY",
    canon_rows=(
        'Francine Ling &amp; Rainee: <span class="text-emerald-400 font-bold">CANONICAL</span>',
        'Steven Transformation Act: <span class="text-emerald-400 font-bold">INCLUDED</span>',
        'Roger Vanderbooben Lore: <span class="text-amber-400 font-bold">UNABRIDGED</span>',
        'Gloria Flamingo Lamp: <span class="text-emerald-400 font-bold">SHATTERED</span>',
    ),
    index_heading="Complete Scene Index:",
    footer_title="HOT SCOOMP UNABRIDGED MASTER CHRONOLOGY",
    footer_line="Compiled &amp; Conditioned • Primary Volume Core Locked • Francine Ling &amp; Rainee Canon",
    nav_group_names=(
        "Ep 0: Foxy Momma",
        "Ep 16: Spring Breakup",
        "Prequel: Alien Butt",
        "Act 1: Domestic War",
        "Act 2: Steve Transformation",
        "Tag: Big Tiddy Steve",
    ),
    nav_group_prefixes=("EP0", "SB", "PRE", "A1", "A2", "TAG"),
    act_keywords=(
        ("EPISODE 0", 0),
        ("SPRING BREAKUP", 1),
        ("SPRING BREAK-UP", 1),
        ("PREQUEL", 2),
        ("ACT ONE", 3),
        ("ACT TWO", 4),
        ("CLIMAX", 5),
        ("TAG", 5),
    ),
    chunk_keywords=(
        ("ACT TWO", 4),
        ("EPISODE TAG", 5),
        ("TAG", 5),
        ("CLIMAX", 5),
    ),
    label_replacements=(
        ("SPRING BREAKUP — SCENE ", "SB "),
        ("SPRING BREAKUP - SCENE ", "SB "),
        ("PREQUEL — SCENE ", "S"),
        ("PREQUEL - SCENE ", "S"),
        ("SCENE ", "S"),
        ("ACT ONE — CHUNK ", "A1 C"),
        ("ACT ONE - CHUNK ", "A1 C"),
        ("ACT TWO — CHUNK ", "A2 C"),
        ("ACT TWO - CHUNK ", "A2 C"),
        ("CHUNK ", "C"),
        ("COLD OPEN", "Cold Open"),
        ("EPISODE TAG", "Tag: Big Tiddy Steve"),
    ),
)


GENERIC_THEME = ReaderTheme(
    page_title="Screenplay Reader",
    brand_badge="SCREENPLAY",
    brand_title="Reader",
    verified_note="✓ Rendered",
    graph_href="",
    hero_h1_html="SCREENPLAY",
    hero_paragraph="",
    canon_heading="DOCUMENT",
    canon_rows=(),
    index_heading="Scene Index:",
    footer_title="",
    footer_line="",
    nav_group_names=("Scenes",),
    nav_group_prefixes=("S",),
)

CSS_LINES: Tuple[str, ...] = (
    "    body { font-family: 'Inter', -apple-system, sans-serif; }",
    "    .screenplay-font { font-family: 'Courier Prime', 'Courier New', monospace; }",
    "    .screenplay-container { max-width: 960px; margin: 0 auto; }",
    "    .scene-heading { font-family: 'Courier Prime', monospace; font-weight: 700; color: #fbbf24; margin-top: 2.25rem; margin-bottom: 0.75rem; text-transform: uppercase; border-left: 3px solid #fbbf24; padding-left: 0.75rem; background: rgba(251, 191, 36, 0.05); padding-top: 0.35rem; padding-bottom: 0.35rem; border-radius: 0 0.375rem 0.375rem 0; }",
    "    .character-cue { font-family: 'Courier Prime', monospace; font-weight: 700; color: #38bdf8; margin-top: 1.5rem; margin-bottom: 0.25rem; text-align: center; letter-spacing: 0.08em; font-size: 1.05rem; }",
    "    .parenthetical { font-family: 'Courier Prime', monospace; font-style: italic; color: #94a3b8; text-align: center; margin-bottom: 0.25rem; font-size: 0.925rem; }",
    "    .dialogue { font-family: 'Courier Prime', monospace; max-width: 620px; margin: 0 auto 1.25rem auto; line-height: 1.6; color: #f1f5f9; font-size: 1rem; }",
    "    .action-block { font-family: 'Courier Prime', monospace; margin: 1rem 0; line-height: 1.65; color: #cbd5e1; font-size: 0.975rem; }",
    "    .transition-cue { font-family: 'Courier Prime', monospace; text-align: right; font-weight: 700; color: #f43f5e; margin: 1.5rem 0; letter-spacing: 0.1em; }",
    "    .chunk-header { background: linear-gradient(135deg, #1e293b, #0f172a); border-left: 4px solid #38bdf8; padding: 1rem 1.25rem; border-radius: 0.5rem; margin: 3rem 0 1.5rem 0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); }",
    "    .act-banner { background: linear-gradient(135deg, #312e81, #1e1b4b); border: 1px solid rgba(129, 140, 248, 0.3); padding: 1.5rem; border-radius: 0.75rem; margin: 4rem 0 2rem 0; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4); }",
    "    .nav-btn { transition: all 0.15s ease-in-out; }",
    "    .nav-btn:hover { transform: translateY(-1px); }",
)


def inline_html(text: str) -> str:
    """Render emphasis only; authored HTML stays escaped plain text."""
    import re
    escaped = html.escape(text)
    escaped = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', escaped)
    return re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', escaped)


def render_reader(document: Document, theme: ReaderTheme = HOT_SCOOMP_THEME) -> str:
    """Renders the document to a complete, standalone HTML reader."""
    sections = build_nav_sections(
        document,
        group_names=list(theme.nav_group_names),
        group_prefixes=list(theme.nav_group_prefixes),
        act_keywords=list(theme.act_keywords),
        chunk_keywords=list(theme.chunk_keywords),
        label_replacements=list(theme.label_replacements),
    )

    out: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en" class="scroll-smooth">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>{html.escape(theme.page_title)}</title>",
    ]
    if theme.tailwind_cdn:
        out.append(f'  <script src="{theme.tailwind_cdn}"></script>')
    else:
        vendored = _vendored_tailwind()
        if vendored:
            out.append(f"  <script>{vendored}</script>")
        else:  # asset missing: degrade to the CDN rather than rendering unstyled
            out.append(f'  <script src="{DEFAULT_TAILWIND_CDN}"></script>')
    out.append("  <style>")
    if theme.fonts_import_url:
        out.append(f"    @import url('{theme.fonts_import_url}');")
    out.extend(CSS_LINES)
    out.extend([
        "  </style>",
        "</head>",
        '<body class="bg-slate-950 text-slate-100 antialiased selection:bg-amber-500 selection:text-slate-950 min-h-screen">',
        "",
        "  <!-- Sticky Top Navigation Bar -->",
        '  <header class="sticky top-0 z-50 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 shadow-xl px-4 py-3">',
        '    <div class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3">',
        '      <div class="flex items-center gap-3">',
        f'        <span class="px-2 py-0.5 bg-amber-500 text-slate-950 rounded text-xs font-black tracking-wider uppercase">{html.escape(theme.brand_badge)}</span>',
        f'        <span class="text-sm font-semibold text-slate-300">{html.escape(theme.brand_title)}</span>',
        f'        <span class="text-xs text-emerald-400 font-mono hidden sm:inline">{html.escape(theme.verified_note)}</span>',
        "      </div>",
        '      <div class="flex items-center gap-2 overflow-x-auto max-w-full pb-1 md:pb-0 text-xs">',
    ])

    for section in sections:
        if not section.links:
            continue
        out.append(
            f'        <a href="#{section.links[0].anchor}" class="nav-btn px-2.5 py-1 bg-slate-800 hover:bg-sky-600 hover:text-white text-slate-300 rounded font-medium border border-slate-700 whitespace-nowrap">{html.escape(section.name)}</a>'
        )

    out.extend([
        f'        <a href="{html.escape(theme.graph_href)}" target="_blank" class="nav-btn px-2.5 py-1 bg-purple-900/80 hover:bg-purple-600 text-purple-200 rounded font-semibold border border-purple-500/50 whitespace-nowrap">📊 Story Graph</a>',
        '        <a href="#top" class="nav-btn px-2.5 py-1 bg-slate-800 hover:bg-amber-500 hover:text-slate-950 text-amber-400 rounded font-semibold border border-amber-500/30 whitespace-nowrap">↑ Top</a>',
        "      </div>",
        "    </div>",
        "  </header>",
        "",
        '  <div id="top" class="screenplay-container px-4 py-8">',
        "",
        "    <!-- Title Card -->",
        '    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 md:p-10 mb-8 shadow-2xl relative overflow-hidden">',
        '      <div class="absolute -right-12 -top-12 w-48 h-48 bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>',
        '      <div class="absolute -left-12 -bottom-12 w-48 h-48 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>',
        '      <div class="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-slate-800 pb-8">',
        "        <div>",
        '          <div class="inline-flex items-center gap-2 px-3 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded-full text-xs font-bold tracking-wider uppercase mb-3">',
        "            <span>TV-14 Animated Comedy</span>",
        "            <span>•</span>",
        "            <span>Primary Volume Focus</span>",
        "          </div>",
        '          <h1 class="text-3xl md:text-5xl font-black text-white tracking-tight leading-none mb-3">',
        f"            {theme.hero_h1_html}",
        "          </h1>",
        '          <p class="text-base md:text-lg text-slate-400 font-medium max-w-2xl">',
        f"            {theme.hero_paragraph}",
        "          </p>",
        "        </div>",
        '        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-4 text-xs font-mono space-y-1 text-slate-400 min-w-[240px]">',
        f'          <div class="text-slate-300 font-semibold mb-1 pb-1 border-b border-slate-800">{html.escape(theme.canon_heading)}</div>',
    ])
    for row in theme.canon_rows:
        out.append(f"          <div>{row}</div>")
    out.extend([
        "        </div>",
        "      </div>",
        "",
        "      <!-- Quick Scene Jump Index -->",
        '      <div class="mt-6 pt-4">',
        f'        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">{html.escape(theme.index_heading)}</div>',
        '        <div class="space-y-3">',
    ])

    for section in sections:
        if not section.links:
            continue
        out.append(
            '          <div class="flex flex-wrap items-center gap-1.5 text-xs">'
            f'            <span class="text-slate-400 font-semibold w-24 shrink-0">{html.escape(section.prefix)}:</span>'
        )
        for link in section.links:
            out.append(
                f'            <a href="#{link.anchor}" title="{html.escape(link.full_title)}" class="px-2 py-0.5 bg-slate-800/80 hover:bg-sky-600 hover:text-white text-slate-300 rounded border border-slate-700/60 transition">{html.escape(link.label)}</a>'
            )
        out.append("          </div>")

    out.extend([
        "        </div>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- Screenplay Script Body -->",
        '    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 md:p-12 shadow-2xl screenplay-body space-y-4">',
    ])

    for block in document.blocks:
        data = f'data-block="{block.id}" data-line="{block.line}"'
        if block.role in (BlockRole.ACT_BANNER, BlockRole.CHUNK_HEADER, BlockRole.SCENE_HEADING):
            css = {
                BlockRole.ACT_BANNER: "act-banner text-2xl md:text-3xl font-black text-amber-400 tracking-tight",
                BlockRole.CHUNK_HEADER: "chunk-header text-xl font-bold text-sky-400",
                BlockRole.SCENE_HEADING: "scene-heading text-lg font-bold tracking-wide mt-8 pt-4",
            }[block.role]
            out.append(
                f'      <div id="{block.id}" {data} class="{css}">{html.escape(block.text)}</div>'
            )
        elif block.role == BlockRole.NOTE:
            out.append(
                f'      <div {data} class="p-4 my-4 bg-slate-800/80 border-l-4 border-amber-500 text-amber-200 text-xs font-sans rounded-r shadow-inner leading-relaxed">{inline_html(block.text)}</div>'
            )
        elif block.role == BlockRole.DIVIDER:
            out.append(f'      <hr {data} class="border-slate-800 my-8">')
        elif block.role == BlockRole.CUE:
            pill = get_character_transformation_pill(block.text) if theme is HOT_SCOOMP_THEME else ''
            if pill:
                out.append(f"      {pill}")
            out.append(
                f'      <div {data} class="character-cue uppercase tracking-wider text-sm font-semibold">{html.escape(block.text)}</div>'
            )
        elif block.role == BlockRole.PARENTHETICAL:
            out.append(
                f'      <div {data} class="parenthetical text-xs text-slate-400">{inline_html(block.text)}</div>'
            )
        elif block.role == BlockRole.DIALOGUE:
            out.append(
                f'      <div {data} class="dialogue font-mono text-sm leading-relaxed text-slate-100">{inline_html(block.text)}</div>'
            )
        else:
            out.append(
                f'      <div {data} class="action-block text-sm leading-relaxed text-slate-300 font-mono">{inline_html(block.text)}</div>'
            )

    out.extend([
        "    </div>",
        "",
        "    <!-- Footer -->",
        '    <footer class="mt-12 py-8 border-t border-slate-800 text-center font-sans text-xs text-slate-500 space-y-2">',
        f'      <p class="font-semibold text-slate-400">{html.escape(theme.footer_title)}</p>',
        f"      <p>{theme.footer_line}</p>",
        '      <div class="pt-4 flex justify-center gap-4 text-sky-400">',
        '        <a href="#top" class="hover:underline">↑ Back to Top</a>',
        "      </div>",
        "    </footer>",
        "",
        "  </div>",
        "</body>",
        "</html>",
    ])

    rendered = '\n'.join(out)
    if theme is not HOT_SCOOMP_THEME:
        rendered = rendered.replace('TV-14 Animated Comedy', 'Authored draft').replace('Primary Volume Focus', 'Review before publishing')
    if not theme.graph_href:
        import re
        rendered = re.sub(r'<a href=""[^>]*>📊 Story Graph</a>', '', rendered)
    if theme.compact:
        import re
        rendered = re.sub(r'<!-- Title Card -->[\s\S]*?<!-- Screenplay Script Body -->',
                          '<!-- Screenplay Script Body -->', rendered)
        compact_css = '''<style>
        .screenplay-container{padding-top:16px!important}
        .screenplay-body{padding:24px!important}
        .act-banner{margin:0 0 18px!important;padding:16px!important;font-size:1.5rem!important}
        .chunk-header{margin:20px 0 12px!important;padding:12px!important;font-size:1.05rem!important}
        .scene-heading{margin-top:18px!important;font-size:1rem!important}
        @media print{body,.screenplay-body{background:white!important;color:black!important}
        header,footer{display:none!important}.screenplay-body{border:0!important;box-shadow:none!important}
        [data-block]{color:black!important;background:white!important;box-shadow:none!important}
        .screenplay-container{max-width:none!important;padding:0!important}}
        </style>'''
        rendered = rendered.replace('</head>', compact_css + '</head>')
    return rendered
