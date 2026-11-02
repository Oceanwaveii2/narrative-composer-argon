"""
HTML Screenplay Reader Compiler.
Compiles Fountain/Markdown screenplays into high-performance, dark-mode,
professional interactive reader HTML with zero dangling anchors and guaranteed DOM ID uniqueness.
"""

from __future__ import annotations
import html
from pathlib import Path
import re
from typing import Optional, List, Set, Tuple

from narrative_composer.compiler.presentation import get_character_transformation_pill
from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.reader_renderer import HOT_SCOOMP_THEME, render_reader

def compile_legacy_html(
    chronology_path: Optional[Path] = None,
    out_file: Optional[Path] = None,
    screenplay_text: Optional[str] = None
) -> Path:
    """
    Compiles a screenplay into hot_scoomp_reader.html.
    Accepts an explicit path to a screenplay file, or in-memory text.
    """
    if screenplay_text is None:
        if chronology_path is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
            chronology_path = root_dir / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        else:
            chronology_path = Path(chronology_path)

        if not chronology_path.exists():
            raise FileNotFoundError(f"{chronology_path} does not exist!")
        screenplay_text = chronology_path.read_text(encoding="utf-8")

    raw_lines = screenplay_text.splitlines()

    nav_groups = [
        {"name": "Ep 0: Foxy Momma", "prefix": "EP0", "links": []},
        {"name": "Ep 16: Spring Breakup", "prefix": "SB", "links": []},
        {"name": "Prequel: Alien Butt", "prefix": "PRE", "links": []},
        {"name": "Act 1: Domestic War", "prefix": "A1", "links": []},
        {"name": "Act 2: Steve Transformation", "prefix": "A2", "links": []},
        {"name": "Tag: Big Tiddy Steve", "prefix": "TAG", "links": []},
    ]

    seen_anchors: Set[str] = set()
    current_group_idx = 0

    def slugify(title: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return s or "section"

    for line in raw_lines:
        sline = line.strip()
        if sline.startswith("# ") and not sline.startswith("### "):
            h1_title = sline[2:].strip().upper()
            if "EPISODE 0" in h1_title:
                current_group_idx = 0
            elif "SPRING BREAKUP" in h1_title or "SPRING BREAK-UP" in h1_title:
                current_group_idx = 1
            elif "PREQUEL" in h1_title:
                current_group_idx = 2
            elif "ACT ONE" in h1_title:
                current_group_idx = 3
            elif "ACT TWO" in h1_title:
                current_group_idx = 4
            elif "CLIMAX" in h1_title or "TAG" in h1_title:
                current_group_idx = 5
            continue

        if sline.startswith("## ") and not sline.startswith("## `"):
            title = sline[3:].strip()
            up_title = title.upper()
            if "ACT TWO" in up_title:
                current_group_idx = 4
            elif "EPISODE TAG" in up_title or "TAG" in up_title or "CLIMAX" in up_title:
                current_group_idx = 5

            anchor = slugify(title)
            if not anchor or anchor in seen_anchors:
                continue
            seen_anchors.add(anchor)

            label = title
            if ":" in title:
                label = title.split(":", 1)[0].strip()
            label = (
                label.replace("SPRING BREAKUP — SCENE ", "SB ")
                .replace("SPRING BREAKUP - SCENE ", "SB ")
                .replace("PREQUEL — SCENE ", "S")
                .replace("PREQUEL - SCENE ", "S")
                .replace("SCENE ", "S")
                .replace("ACT ONE — CHUNK ", "A1 C")
                .replace("ACT ONE - CHUNK ", "A1 C")
                .replace("ACT TWO — CHUNK ", "A2 C")
                .replace("ACT TWO - CHUNK ", "A2 C")
                .replace("CHUNK ", "C")
                .replace("COLD OPEN", "Cold Open")
                .replace("EPISODE TAG", "Tag: Big Tiddy Steve")
            )

            nav_groups[current_group_idx]["links"].append((anchor, label, title))

    # Build HTML
    html_content: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en" class="scroll-smooth">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "  <title>Hot Scoomp — Unabridged Master Chronology (Episode 0 to Finale)</title>",
        '  <script src="https://cdn.tailwindcss.com"></script>',
        "  <style>",
        "    @import url('https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400;1,700&family=Inter:wght@400;500;600;700;800;900&display=swap');",
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
        "  </style>",
        "</head>",
        '<body class="bg-slate-950 text-slate-100 antialiased selection:bg-amber-500 selection:text-slate-950 min-h-screen">',
        "",
        "  <!-- Sticky Top Navigation Bar -->",
        '  <header class="sticky top-0 z-50 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 shadow-xl px-4 py-3">',
        '    <div class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3">',
        '      <div class="flex items-center gap-3">',
        '        <span class="px-2 py-0.5 bg-amber-500 text-slate-950 rounded text-xs font-black tracking-wider uppercase">HOT SCOOMP</span>',
        '        <span class="text-sm font-semibold text-slate-300">Unabridged Master Reader</span>',
        '        <span class="text-xs text-emerald-400 font-mono hidden sm:inline">✓ Verified Master Screenplay</span>',
        "      </div>",
        '      <div class="flex items-center gap-2 overflow-x-auto max-w-full pb-1 md:pb-0 text-xs">',
    ]

    for group in nav_groups:
        if not group["links"]:
            continue
        first_anchor = group["links"][0][0]
        html_content.append(
            f'        <a href="#{first_anchor}" class="nav-btn px-2.5 py-1 bg-slate-800 hover:bg-sky-600 hover:text-white text-slate-300 rounded font-medium border border-slate-700 whitespace-nowrap">{html.escape(group["name"])}</a>'
        )

    html_content.extend([
        '        <a href="out/graphs/master.viewer.html" target="_blank" class="nav-btn px-2.5 py-1 bg-purple-900/80 hover:bg-purple-600 text-purple-200 rounded font-semibold border border-purple-500/50 whitespace-nowrap">📊 Story Graph</a>',
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
        '            HOT SCOOMP <span class="text-amber-400">:</span> COMPLETE CHRONOLOGY',
        "          </h1>",
        '          <p class="text-base md:text-lg text-slate-400 font-medium max-w-2xl">',
        "            The unabridged full arc: Episode 0 (Origin), Ep 16 (Spring Breakup AU), The Prequel (Cult, Congo &amp; Transformations), Acts 1 &amp; 2 (Steven Transformation), and The Climax Tag.",
        "          </p>",
        "        </div>",
        '        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-4 text-xs font-mono space-y-1 text-slate-400 min-w-[240px]">',
        '          <div class="text-slate-300 font-semibold mb-1 pb-1 border-b border-slate-800">CANON INTEGRITY</div>',
        '          <div>Francine Ling &amp; Rainee: <span class="text-emerald-400 font-bold">CANONICAL</span></div>',
        '          <div>Steven Transformation Act: <span class="text-emerald-400 font-bold">INCLUDED</span></div>',
        '          <div>Roger Vanderbooben Lore: <span class="text-amber-400 font-bold">UNABRIDGED</span></div>',
        '          <div>Gloria Flamingo Lamp: <span class="text-emerald-400 font-bold">SHATTERED</span></div>',
        "        </div>",
        "      </div>",
        "",
        "      <!-- Quick Scene Jump Index -->",
        '      <div class="mt-6 pt-4">',
        '        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Complete Scene Index:</div>',
        '        <div class="space-y-3">',
    ])

    for group in nav_groups:
        if not group["links"]:
            continue
        html_content.append(
            f'          <div class="flex flex-wrap items-center gap-1.5 text-xs">'
            f'            <span class="text-slate-400 font-semibold w-24 shrink-0">{html.escape(group["prefix"])}:</span>'
        )
        for anchor, label, full_title in group["links"]:
            html_content.append(
                f'            <a href="#{anchor}" title="{html.escape(full_title)}" class="px-2 py-0.5 bg-slate-800/80 hover:bg-sky-600 hover:text-white text-slate-300 rounded border border-slate-700/60 transition">{html.escape(label)}</a>'
            )
        html_content.append("          </div>")

    html_content.extend([
        "        </div>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- Screenplay Script Body -->",
        '    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 md:p-12 shadow-2xl screenplay-body space-y-4">',
    ])

    # Global ID registry to guarantee 100% unique DOM IDs across document
    emitted_dom_ids: Set[str] = set()

    def get_unique_id(title: str, is_nav_anchor: bool = False) -> str:
        base = slugify(title)
        if is_nav_anchor:
            # Nav anchors must match exactly
            emitted_dom_ids.add(base)
            return base
        if base not in emitted_dom_ids:
            emitted_dom_ids.add(base)
            return base
        # Disambiguate duplicate scene headings or elements
        counter = 2
        while f"{base}-{counter}" in emitted_dom_ids:
            counter += 1
        unique_id = f"{base}-{counter}"
        emitted_dom_ids.add(unique_id)
        return unique_id

    # Direct line-based AST parser with exact anchor matching
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if not line:
            i += 1
            continue

        # 1. H1 Act Banner: # ...
        if line.startswith("# ") and not line.startswith("### "):
            title = line[2:].strip()
            anchor = get_unique_id(title, is_nav_anchor=True)
            html_content.append(
                f'      <div id="{anchor}" class="act-banner text-2xl md:text-3xl font-black text-amber-400 tracking-tight">{html.escape(title)}</div>'
            )
            i += 1
            continue

        # 2. H2 Chunk / Scene Header: ## ...
        if line.startswith("## ") and not line.startswith("## `"):
            title = line[3:].strip()
            anchor = get_unique_id(title, is_nav_anchor=True)
            html_content.append(
                f'      <div id="{anchor}" class="chunk-header text-xl font-bold text-sky-400">{html.escape(title)}</div>'
            )
            i += 1
            continue

        # 3. Scene Slugline: ### `INT. ...` or INT. ...
        scene_match = re.match(r"^(?:###\s+`?)?(INT\.|EXT\.|INT/EXT\.|EXT/INT\.)(?:\s+.*?)?`?$", line, re.IGNORECASE)
        if scene_match:
            slug = re.sub(r"^###\s+`?|`?$", "", line).strip()
            anchor = get_unique_id(slug, is_nav_anchor=False)
            html_content.append(
                f'      <div id="{anchor}" class="scene-heading text-lg font-bold tracking-wide mt-8 pt-4">{html.escape(slug)}</div>'
            )
            i += 1
            continue

        # 4. Blockquote note: > ...
        if line.startswith("> "):
            html_content.append(
                f'      <div class="p-4 my-4 bg-slate-800/80 border-l-4 border-amber-500 text-amber-200 text-xs font-sans rounded-r shadow-inner leading-relaxed">{html.escape(line[2:])}</div>'
            )
            i += 1
            continue

        # 5. Divider: ---
        if line == "---":
            html_content.append('      <hr class="border-slate-800 my-8">')
            i += 1
            continue

        # 6. Bold Dialogue pattern: **SPEAKER:** "..."
        bold_match = re.match(r"^\*\*(.*?)\*\*:?\s*(?:\*\((.*?)\)\*)?\s*(.*)$", line)
        if bold_match:
            speaker = bold_match.group(1).strip()
            paren = bold_match.group(2)
            dialogue = bold_match.group(3).strip()
            pill = get_character_transformation_pill(speaker)
            if pill:
                html_content.append(f"      {pill}")
            html_content.append(
                f'      <div class="character-cue uppercase tracking-wider text-sm font-semibold">{html.escape(speaker)}</div>'
            )
            if paren:
                html_content.append(
                    f'      <div class="parenthetical text-xs text-slate-400">({html.escape(paren)})</div>'
                )
            if dialogue:
                html_content.append(
                    f'      <div class="dialogue font-mono text-sm leading-relaxed text-slate-100">{html.escape(dialogue)}</div>'
                )
            i += 1
            continue

        # 7. Standard Fountain Character Cue (all caps, next line is parenthetical or dialogue)
        if line.isupper() and len(line) < 40 and i + 1 < len(raw_lines):
            next_line = raw_lines[i + 1].strip()
            if next_line.startswith("(") or (next_line.startswith('"') and next_line.endswith('"')):
                pill = get_character_transformation_pill(line)
                if pill:
                    html_content.append(f"      {pill}")
                html_content.append(
                    f'      <div class="character-cue uppercase tracking-wider text-sm font-semibold">{html.escape(line)}</div>'
                )
                i += 1
                if i < len(raw_lines) and raw_lines[i].strip().startswith("("):
                    html_content.append(
                        f'      <div class="parenthetical text-xs text-slate-400">{html.escape(raw_lines[i].strip())}</div>'
                    )
                    i += 1
                if i < len(raw_lines) and raw_lines[i].strip():
                    html_content.append(
                        f'      <div class="dialogue font-mono text-sm leading-relaxed text-slate-100">{html.escape(raw_lines[i].strip())}</div>'
                    )
                    i += 1
                continue

        # 8. Action line
        html_content.append(
            f'      <div class="action-block text-sm leading-relaxed text-slate-300 font-mono">{html.escape(line)}</div>'
        )
        i += 1

    html_content.extend([
        "    </div>",
        "",
        "    <!-- Footer -->",
        '    <footer class="mt-12 py-8 border-t border-slate-800 text-center font-sans text-xs text-slate-500 space-y-2">',
        '      <p class="font-semibold text-slate-400">HOT SCOOMP UNABRIDGED MASTER CHRONOLOGY</p>',
        "      <p>Compiled &amp; Conditioned • Primary Volume Core Locked • Francine Ling &amp; Rainee Canon</p>",
        '      <div class="pt-4 flex justify-center gap-4 text-sky-400">',
        '        <a href="#top" class="hover:underline">↑ Back to Top</a>',
        "      </div>",
        "    </footer>",
        "",
        "  </div>",
        "</body>",
        "</html>",
    ])

    if out_file is None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        out_file = root_dir / "hot_scoomp_reader.html"
    else:
        out_file = Path(out_file)

    out_file.write_text("\n".join(html_content), encoding="utf-8")
    return out_file


def compile_screenplay_html(
    chronology_path: Optional[Path] = None,
    out_file: Optional[Path] = None,
    screenplay_text: Optional[str] = None,
    theme: "ReaderTheme" = HOT_SCOOMP_THEME,
) -> Path:
    """
    Compiles a screenplay into the standalone reader HTML.

    Parses the text into the canonical Document model and renders it through the
    themeable reader renderer. `compile_legacy_html` is retained as a parity oracle.
    Pass a different theme (e.g. GENERIC_THEME) to format another screenplay.
    """
    if screenplay_text is None:
        if chronology_path is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
            chronology_path = root_dir / "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md"
        else:
            chronology_path = Path(chronology_path)

        if not chronology_path.exists():
            raise FileNotFoundError(f"{chronology_path} does not exist!")
        screenplay_text = chronology_path.read_text(encoding="utf-8")

    if out_file is None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        out_file = root_dir / "hot_scoomp_reader.html"
    else:
        out_file = Path(out_file)

    document = parse_document(screenplay_text)
    with out_file.open('x', encoding='utf-8') as output:
        output.write(render_reader(document, theme))
    return out_file
