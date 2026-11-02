"""
Ingest an arbitrary prose-style screenplay ("script prose") into the node system.

Many drafts are written as prose with `**NAME**` cue lines, markdown parentheticals and
bold sound effects, plus `###` section headers. This module adapts that shape into the
Fountain-ish form the parser understands, auto-discovers the cast (a new universe has no
character configs), builds the unified node store, and renders a standalone reader.

    python -m narrative_composer.story --file PATH --out out/story --title "Episode 1"
"""

from __future__ import annotations

import argparse
import json
import re
import html
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from narrative_composer.compiler.document import parse_document
from narrative_composer.compiler.identity import save_entries, sidecar_path
from narrative_composer.compiler.reader_renderer import GENERIC_THEME, render_reader
from narrative_composer.graph.discover import apply_discovery, discover
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import EntityDef, StateDef
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.store import build_store, summary

EMPTY_MANIFEST: Dict[str, Any] = {
    "manifest_name": "auto",
    "version": "1.0.0",
    "facts": {},
    "initial_beliefs": {},
    "props": {},
    "character_locations": {},
    "room_topology": {},
    "beats": {},
}

_CUE_LINE = re.compile(r"^\*\*([^*]+?)\*\*\s*$")
_HEADING = re.compile(r"^(#{3,6})\s+(.*)$")
_SFX_MARKS = "!?—–！？"


def _looks_like_sfx(name: str) -> bool:
    """Bold lines that are sound, not speakers (SMACK!, 轰——！！)."""
    return any(mark in name for mark in _SFX_MARKS)


def _looks_like_cue(name: str) -> bool:
    """A speaker cue is short, unbracketed, and has no label colon or sentence punctuation."""
    if not name or len(name) > 40:
        return False
    if any(mark in name for mark in _SFX_MARKS):
        return False
    if name.startswith("[") or name.endswith("]") or ":" in name or "：" in name:
        return False
    if any(ch in name for ch in "。，、；"):
        return False
    return True


_EMPHASIS = re.compile(r"(?<!\*)\*([^*\n]{1,120})\*(?!\*)")

# Observer-filter phrases the prose diagnostics flag; replaced with direct action.
_FILTER_FIXES = (
    (re.compile(r"\bcaught sight of\b", re.IGNORECASE), "spotted"),
    (re.compile(r"\bcaught a glimpse of\b", re.IGNORECASE), "glimpsed"),
)


def condition_text(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Applies safe, deterministic conditioning: strips leftover markdown emphasis, replaces
    observer-filter phrases, and tidies spacing, then measures prose quality (filter words,
    emotion labels, cadence).
    """
    from collections import Counter

    from narrative_composer.models.ast_nodes import ASTNodeType
    from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer

    conditioned = _EMPHASIS.sub(r"\1", text)
    filter_fixes = 0
    for pattern, replacement in _FILTER_FIXES:
        conditioned, count = pattern.subn(replacement, conditioned)
        filter_fixes += count
    conditioned = re.sub(r"[ \t]+([,.;:!?])", r"\1", conditioned)
    conditioned = re.sub(r"[ \t]{2,}", " ", conditioned)

    elements = FountainParser.parse(conditioned)
    actions = [e.content for e in elements if e.node_type == ASTNodeType.ACTION]
    spans = [ProseDiagnosticsAnalyzer.analyze(action) for action in actions]
    burstiness = (
        round(sum(span.burstiness_score for span in spans) / len(spans), 2) if spans else 0.0
    )
    metrics = {
        "action_spans": len(actions),
        "filter_fixes": filter_fixes,
        "filter_words": sum(span.filter_word_count for span in spans),
        "emotion_labels": sum(len(span.label_examples) for span in spans),
        "mean_burstiness": burstiness,
        "spans_with_warnings": sum(1 for span in spans if span.warnings),
        "common_warnings": Counter(
            warning.split(":")[0] for span in spans for warning in span.warnings
        ).most_common(5),
    }
    return conditioned, metrics


def adapt_story(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Normalises prose-script formatting into the parser's Fountain-ish grammar:

      * keeps the top-level title, drops front-matter dossiers before the first PART
      * `###`/`####` section headers become chunk headers (`##`)
      * `**NAME**` cue lines become `**NAME:**` so the parser opens a character block
      * bold sound effects become blockquote notes (`> SFX: ...`)
      * code fences are removed, trailing whitespace stripped
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalised.split("\n")

    stats: Dict[str, Any] = {"dropped_front_matter": 0, "cues": 0, "sfx": 0, "sections": 0}
    part_index = next((i for i, line in enumerate(lines) if line.strip().startswith("## PART")), None)
    if part_index is not None:
        title_lines = [
            line for line in lines[:part_index]
            if line.strip().startswith("# ") and not line.strip().startswith("## ")
        ]
        stats["dropped_front_matter"] = max(0, part_index - len(title_lines))
        lines = title_lines + [""] + lines[part_index:]

    output: List[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            continue

        heading = _HEADING.match(stripped)
        if heading:
            output.append(f"## {heading.group(2).strip()}")
            stats["sections"] += 1
            continue

        cue = _CUE_LINE.match(stripped)
        if cue:
            name = cue.group(1).strip()
            if _looks_like_cue(name):
                output.append(f"**{name}:**")
                stats["cues"] += 1
            elif _looks_like_sfx(name):
                output.append(f"> SFX: {name}")
                stats["sfx"] += 1
            else:
                # Bracketed UI readouts, bolded sentences: annotations, not speakers.
                output.append(f"> {name}")
                stats["annotations"] = stats.get("annotations", 0) + 1
            continue

        output.append(line)

    # Collapse runs of blank lines so the reader keeps its rhythm.
    collapsed: List[str] = []
    blank = 0
    for line in output:
        if line.strip():
            blank = 0
            collapsed.append(line)
        else:
            blank += 1
            if blank <= 1:
                collapsed.append("")
    return "\n".join(collapsed).strip("\n") + "\n", stats


def _starter_registry(cast: Dict[str, Dict[str, Any]], canon: str) -> Dict[str, EntityDef]:
    """Seeds entities from a cast file so variants (e.g. EN + ZH cues) share one identity."""
    registry: Dict[str, EntityDef] = {}
    for entity_id, spec in cast.items():
        display = spec.get("display_name", entity_id)
        registry[entity_id] = EntityDef(
            entity_id=entity_id,
            display_name=display,
            aliases=list(spec.get("aliases", [])),
            canons=[canon],
            base_state="base",
            states=[
                StateDef(
                    id=f"{entity_id}.state.base",
                    slug="base",
                    label=display,
                    canons=[canon],
                )
            ],
        )
    return registry


def story_theme(title: str, subtitle: str = "", badge: str = "STORY") -> Any:
    return replace(
        GENERIC_THEME,
        page_title=title,
        brand_badge=badge,
        brand_title="Story Reader",
        hero_h1_html=html.escape(title),
        hero_paragraph=subtitle,
        index_heading="Sections:",
        footer_title=title,
        footer_line="Rendered from the unified node store",
        nav_group_names=("Sections",),
        nav_group_prefixes=("S",),
    )


def run_story(
    source_path: Path,
    out_dir: Path,
    title: Optional[str] = None,
    canon: str = "story",
    slug: Optional[str] = None,
    cast: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Preserves the source, discovers candidates, and prepares a new project."""
    source_path = Path(source_path)
    source_bytes = source_path.read_bytes()
    adapted = source_bytes.decode('utf-8')
    adapt_stats = {'status':'not run', 'source':'preserved byte-for-byte'}
    conditioning = {'status':'not run; propose and review separately'}

    out = Path(out_dir)
    if any((out / name).exists() for name in ('story.md','manifest.json','nodes.json','characters')):
        raise FileExistsError('Intake output already contains a project; choose a new folder to preserve authored edits')
    out.mkdir(parents=True, exist_ok=True)
    slug = slug or re.sub(r"[^a-z0-9]+", "-", (title or source_path.stem).lower()).strip("-") or "story"
    title = title or source_path.stem

    story_path = out / "story.md"
    story_path.write_bytes(source_bytes)

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(EMPTY_MANIFEST, indent=2) + "\n", encoding="utf-8")

    elements = FountainParser.parse(adapted)
    starter = StoryGraph.from_registry(_starter_registry(cast or {}, canon))
    discovered = discover(elements, starter, canon=canon, run_id=slug)
    graph = apply_discovery(starter, discovered)
    registry = graph.entities
    entity_dir = out / 'characters'
    entity_dir.mkdir()
    for entity_id, definition in registry.items():
        (entity_dir / f'{entity_id}.json').write_text(definition.model_dump_json(indent=2) + '\n', encoding='utf-8')

    store = build_store(
        script_path=story_path,
        manifest_path=manifest_path,
        canon=canon,
        registry=registry,
        text=adapted,
        use_cache=False,
    )
    store.save(out / "nodes.json")
    if store.meta.get("id_map"):
        save_entries(sidecar_path(story_path), store.meta["id_map"])

    document = parse_document(adapted)
    reader = out / "reader.html"
    reader.write_text(
        render_reader(document, story_theme(title, f"Auto-discovered cast of {len(registry)}")),
        encoding="utf-8",
    )

    info = summary(store)
    diagnostics = store.meta.get("diagnostics", [])
    report = {
        "story": title,
        "source": str(source_path),
        "canon": canon,
        "adaptation": adapt_stats,
        "conditioning": conditioning,
        "summary": info,
        "entities": sorted(registry),
        "diagnostics": diagnostics,
        "artifacts": {
            "story": str(story_path),
            "nodes": str(out / "nodes.json"),
            "reader": str(reader),
            'manifest': str(manifest_path),
            'entity_dir': str(entity_dir),
        },
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="narrative_composer.story", description="Ingest a new story")
    parser.add_argument("--file", required=True, help="Source screenplay/prose text")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--title", default=None, help="Reader title")
    parser.add_argument("--canon", default="story", help="Canon name for discovered entities")
    parser.add_argument("--cast", default=None, help="JSON cast file: {entity_id: {display_name, aliases}}")
    args = parser.parse_args(argv)

    cast = json.loads(Path(args.cast).read_text(encoding="utf-8")) if args.cast else None
    report = run_story(
        Path(args.file), Path(args.out), title=args.title, canon=args.canon, cast=cast
    )
    info = report["summary"]
    print(f"story:      {report['story']}")
    print(f"adapted:    {report['adaptation']}")
    print(f"cast:       {', '.join(report['entities'][:12])}{'…' if len(report['entities']) > 12 else ''}")
    print(f"nodes:      {info['nodes']:,}  edges: {info['edges']:,}  kinds: {info['kinds']}")
    print(f"diagnostics:{info['diagnostics']} ({info['errors']} errors, {info['addressed']} addressed)")
    for diagnostic in report["diagnostics"][:8]:
        print(f"  [{diagnostic['severity']:7}] {diagnostic['rule_id']:32} {diagnostic['node_id'] or '(store)'}")
    print(f"reader:     {report['artifacts']['reader']}")
    print(f"nodes.json: {report['artifacts']['nodes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
