"""
Canonical screenplay document model.

The document is the single source of truth that renderers (reader HTML, an eventual
editor, and print/DesignCraft) project from. Blocks carry stable IDs so a node can be
addressed for selective re-cook, and the original source lines are retained verbatim so
`parse_document()` -> `to_fountain()` is lossless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple
import hashlib
import re

from narrative_composer.models.ast_nodes import ASTNodeType
from narrative_composer.parser.fountain_lexer import FountainParser


class BlockRole(str, Enum):
    ACT_BANNER = "act_banner"
    CHUNK_HEADER = "chunk_header"
    SCENE_HEADING = "scene_heading"
    NOTE = "note"
    DIVIDER = "divider"
    CUE = "cue"
    PARENTHETICAL = "parenthetical"
    DIALOGUE = "dialogue"
    ACTION = "action"


# Heading / cue grammar, kept consistent with the Fountain lexer and the reader.
SCENE_REGEX = re.compile(
    r"^(?:#{1,6}\s+`?)?(INT\.|EXT\.|INT/EXT\.|EXT/INT\.)(?:\s+.*?)?`?$",
    re.IGNORECASE,
)
BOLD_CUE_REGEX = re.compile(r"^\*\*(.*?)\*\*:?\s*(?:\*\((.*?)\)\*)?\s*(.*)$")


def slugify(title: str) -> str:
    """Lowercase, hyphenated anchor slug (matches the reader's historical anchors).

    Titles with no Latin characters (e.g. Chinese section headers) fall back to a
    deterministic hash so they get distinct, stable anchors instead of colliding on
    "section".
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "u" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    return slug


class IdAllocator:
    """Deterministic ID allocation: fixed IDs for headings, deduplicated for the rest."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def fixed(self, base: str) -> str:
        """Heading anchors keep their exact slug so navigation links stay valid."""
        self._used.add(base)
        return base

    def unique(self, base: str) -> str:
        if base not in self._used:
            self._used.add(base)
            return base
        counter = 2
        while f"{base}-{counter}" in self._used:
            counter += 1
        unique_id = f"{base}-{counter}"
        self._used.add(unique_id)
        return unique_id


@dataclass
class Block:
    """One addressable unit of the screenplay."""

    id: str
    role: BlockRole
    text: str
    line: int
    raw: str = ""
    speaker: Optional[str] = None
    start: int = 0
    end: int = 0

    @property
    def is_heading(self) -> bool:
        return self.role in (BlockRole.ACT_BANNER, BlockRole.CHUNK_HEADER, BlockRole.SCENE_HEADING)


@dataclass
class Scene:
    """A scene: one slugline plus the blocks that follow it."""

    id: str
    heading: Optional[Block]
    blocks: List[Block] = field(default_factory=list)


@dataclass
class Document:
    """Parsed screenplay: ordered blocks, derived scenes, and the original lines."""

    blocks: List[Block]
    lines: List[str]
    scenes: List[Scene] = field(default_factory=list)

    @property
    def source(self) -> str:
        return "\n".join(self.lines)

    def to_fountain(self) -> str:
        """Lossless serialization back to the original screenplay text."""
        return self.source

    def block_by_id(self, block_id: str) -> Block:
        for block in self.blocks:
            if block.id == block_id:
                return block
        raise KeyError(f"Unknown block id: {block_id!r}")

    def blocks_in(self, role: BlockRole) -> List[Block]:
        return [b for b in self.blocks if b.role == role]


def _content_block_id(role: BlockRole, text: str) -> str:
    """
    Content-addressed block ID.

    Inserting or deleting unrelated lines no longer renames existing blocks (line-based
    IDs shifted on every insertion). Editing a block's own text produces a new ID, which
    is expected for a content-addressed scheme.
    """
    digest = hashlib.sha1(f"{role.value}\x00{text}".encode("utf-8")).hexdigest()[:8]
    return f"{role.value}-{digest}"


def _line_text(lines: List[str], line_number: int, fallback: str = "") -> str:
    """Verbatim source line (stripped), used for display so quotes/emphasis survive."""
    if 0 < line_number <= len(lines):
        return lines[line_number - 1].strip()
    return fallback


def _raw_line(lines: List[str], line_number: int, fallback: str = "") -> str:
    """Unmodified source line, preserving indentation and trailing whitespace.

    `raw` is what lets a Document round-trip losslessly; stripping it here would make
    `to_fountain()` silently drop trailing spaces from every edited line.
    """
    if 0 < line_number <= len(lines):
        return lines[line_number - 1]
    return fallback


def _inline_dialogue_display(elements, index: int, lines: List[str]) -> str:
    """
    Reconstructs the displayed dialogue for a cue/dialogue pair written on one line.

    The AST stores dialogue semantically (without surrounding quotes); the reader renders
    the source text, so '**DANA:** \"Who?\"' must display as \"Who?\" and not Who?.
    """
    element = elements[index]
    line = _line_text(lines, element.line_number, element.content)
    if not line:
        return element.content

    same_line_cue = None
    for j in range(index - 1, -1, -1):
        previous = elements[j]
        if previous.line_number != element.line_number:
            break
        if previous.node_type == ASTNodeType.CHARACTER:
            same_line_cue = previous
            break
    if same_line_cue is None:
        return line  # standalone dialogue: render the line verbatim

    remainder = re.sub(r"^\*\*[^*]+\*\*:?\s*", "", line)
    paren_text = None
    for j in range(index - 1, -1, -1):
        previous = elements[j]
        if previous.line_number != element.line_number:
            break
        if previous.node_type == ASTNodeType.PARENTHETICAL:
            paren_text = previous.content
            break
    if paren_text:
        remainder = remainder.strip()
        for candidate in (paren_text, "*" + paren_text + "*"):
            if remainder.startswith(candidate):
                remainder = remainder[len(candidate):].strip()
                break
    return remainder.strip()


_ROLE_BY_NODE = {
    ASTNodeType.ACT_BANNER: BlockRole.ACT_BANNER,
    ASTNodeType.CHUNK_HEADER: BlockRole.CHUNK_HEADER,
    ASTNodeType.SCENE_HEADING: BlockRole.SCENE_HEADING,
    ASTNodeType.NOTE: BlockRole.NOTE,
    ASTNodeType.DIVIDER: BlockRole.DIVIDER,
    ASTNodeType.PARENTHETICAL: BlockRole.PARENTHETICAL,
    ASTNodeType.DIALOGUE: BlockRole.DIALOGUE,
}


def parse_document(text: str, elements: Optional[List[Any]] = None) -> Document:
    """
    Builds a Document from the Fountain AST.

    Classification comes from the single parser (`FountainParser`); display text is
    taken from the source line so quotes and emphasis survive rendering. Blocks carry
    stable IDs and the original source lines are retained for a lossless round-trip.

    Pass `elements` to reuse an already-parsed AST instead of parsing twice.
    """
    source = text
    lines = source.split("\n")
    elements = elements if elements is not None else FountainParser.parse(source)
    allocator = IdAllocator()
    blocks: List[Block] = []
    cursors: dict[int, int] = {}

    for index, element in enumerate(elements):
        node = element.node_type
        line_no = element.line_number

        if node in _ROLE_BY_NODE:
            role = _ROLE_BY_NODE[node]
            display = element.content
            if role in (BlockRole.ACT_BANNER, BlockRole.CHUNK_HEADER):
                # Unique, not fixed: two sections with the same title must not share an
                # anchor (CJK titles used to collapse to the same slug).
                block_id = allocator.unique(slugify(display))
            elif role == BlockRole.SCENE_HEADING:
                block_id = allocator.unique(slugify(display))
            elif role == BlockRole.DIVIDER:
                display = ""
                block_id = allocator.unique(_content_block_id(role, display))
            elif role == BlockRole.NOTE:
                display = display.strip()
                block_id = allocator.unique(_content_block_id(role, display))
            elif role == BlockRole.PARENTHETICAL:
                block_id = allocator.unique(_content_block_id(role, display))
            else:  # DIALOGUE
                display = _inline_dialogue_display(elements, index, lines)
                block_id = allocator.unique(_content_block_id(role, display))

        elif node == ASTNodeType.CHARACTER:
            following = elements[index + 1].node_type if index + 1 < len(elements) else None
            character_line = _line_text(lines, line_no, element.content)
            # An explicit markdown cue (**NAME:**) is always a cue, even without dialogue.
            is_cue = (
                following in (ASTNodeType.PARENTHETICAL, ASTNodeType.DIALOGUE)
                or character_line.startswith("**")
            )
            if is_cue:
                role = BlockRole.CUE
                display = element.content
                block_id = allocator.unique(_content_block_id(role, display))
            else:
                # A caps line that introduces nothing (sound effect, label, shout).
                # The reader has always treated these as action.
                role = BlockRole.ACTION
                display = character_line
                block_id = allocator.unique(_content_block_id(role, display))

        else:  # ACTION, TRANSITION, LEGACY_HEADING
            role = BlockRole.ACTION
            # Inline markdown emphasis is never rendered, so strip the markers rather
            # than leaking '**' into the reader.
            display = _line_text(lines, line_no, element.content).strip()
            if display.startswith('! '):
                display = display[2:]
            block_id = allocator.unique(_content_block_id(role, display))

        raw = _raw_line(lines, line_no, element.content)
        start = raw.find(display, cursors.get(line_no, 0)) if display else 0
        if start < 0:
            # Display-normalized action (e.g. inline emphasis) owns the entire line.
            start, end = 0, len(raw)
        else:
            end = start + len(display)
        cursors[line_no] = end
        blocks.append(
            Block(
                id=block_id,
                role=role,
                text=display,
                line=line_no,
                raw=_raw_line(lines, line_no, element.content),
                speaker=element.speaker,
                start=start,
                end=end,
            )
        )

    return Document(blocks=blocks, lines=lines, scenes=_build_scenes(blocks))


def replace_block_text(text: str, block_id: str, new_display: str) -> str:
    """
    Rewrites one block's display text into the source and returns the new source.

    The displayed text is replaced inside the block's own source line, which preserves
    surrounding markdown (headings, bold cues, blockquote markers). When the display text
    is not a literal substring of the line (e.g. an action line whose bold markers were
    stripped for display), the whole line is replaced.
    """
    if "\n" in new_display or "\r" in new_display:
        raise ValueError("A block edit must be a single line")

    document = parse_document(text)
    block = document.block_by_id(block_id)  # raises KeyError for unknown ids

    lines = text.split("\n")
    index = block.line - 1
    if not (0 <= index < len(lines)):
        raise KeyError(f"Block {block_id!r} points at missing line {block.line}")

    line = lines[index]
    lines[index] = line[:block.start] + new_display + line[block.end:]
    return "\n".join(lines)


def rebuild_scenes(document: Document) -> None:
    """Recomputes scene grouping after block IDs have been stabilised."""
    document.scenes = _build_scenes(document.blocks)


def _build_scenes(blocks: List[Block]) -> List[Scene]:
    """Groups blocks under their scene slugline (front matter gets a synthetic scene)."""
    scenes: List[Scene] = []
    current: Optional[Scene] = None
    for block in blocks:
        if block.role == BlockRole.SCENE_HEADING:
            current = Scene(id=block.id, heading=block, blocks=[])
            scenes.append(current)
            continue
        if current is None:
            current = Scene(id="front-matter", heading=None, blocks=[])
            scenes.append(current)
        current.blocks.append(block)
    return scenes


@dataclass
class NavLink:
    anchor: str
    label: str
    full_title: str


@dataclass
class NavSection:
    name: str
    prefix: str
    links: List[NavLink] = field(default_factory=list)


def build_nav_sections(
    document: Document,
    group_names: List[str],
    group_prefixes: List[str],
    act_keywords: List[Tuple[str, int]],
    chunk_keywords: List[Tuple[str, int]],
    label_replacements: List[Tuple[str, str]],
) -> List[NavSection]:
    """
    Builds navigation sections from act banners and chunk headers.

    The first pass mirrors the historical reader: act banners select the active group,
    chunk headers optionally re-select it and contribute links (deduplicated by anchor).
    """
    sections = [NavSection(name=n, prefix=p) for n, p in zip(group_names, group_prefixes)]
    seen: set[str] = set()
    active = 0

    for block in document.blocks:
        if block.role == BlockRole.ACT_BANNER:
            upper = block.text.upper()
            for keyword, index in act_keywords:
                if keyword in upper:
                    active = index
                    break
            continue

        if block.role != BlockRole.CHUNK_HEADER:
            continue

        upper = block.text.upper()
        for keyword, index in chunk_keywords:
            if keyword in upper:
                active = index
                break

        if block.id in seen:
            continue
        seen.add(block.id)

        title = block.text
        label = title.split(":", 1)[0].strip() if ":" in title else title
        for pattern, replacement in label_replacements:
            label = label.replace(pattern, replacement)

        if not (0 <= active < len(sections)):
            active = 0
        sections[active].links.append(NavLink(anchor=block.id, label=label, full_title=title))

    return sections
