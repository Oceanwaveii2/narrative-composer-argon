"""
Fountain & Markdown Screenplay AST Lexer / Parser.
Converts raw screenplay text into typed AST elements with accurate line numbers and speaker tags.
"""

from __future__ import annotations
import re
from typing import List, Optional
from ..models.ast_nodes import ASTElement, ASTNodeType


class FountainParser:
    SCENE_REGEX = re.compile(
        r"^(?:#{1,6}\s+`?)?(INT\.|EXT\.|INT/EXT\.|EXT/INT\.)(?:\s+.*?)?`?$",
        re.IGNORECASE
    )
    TRANSITION_REGEX = re.compile(
        r"^(?:>|FADE\s+IN:|FADE\s+OUT\.|CUT\s+TO:|DISSOLVE\s+TO:|SMASH\s+CUT\s+TO:)",
        re.IGNORECASE
    )
    PAREN_REGEX = re.compile(r"^\((.*?)\)$")

    @classmethod
    def parse(cls, script_text: str) -> List[ASTElement]:
        """
        Parses screenplay text (standard Fountain or Markdown-styled) into a list of ASTElement nodes.
        """
        ast: List[ASTElement] = []
        # Windows editors routinely save with a UTF-8 BOM; left in place it corrupts
        # the first line, turning a scene heading into a phantom character cue.
        script_text = script_text.lstrip("\ufeff")
        lines = script_text.split("\n")
        current_speaker: Optional[str] = None

        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                current_speaker = None
                continue
            if line.startswith('! '):
                ast.append(ASTElement(node_type=ASTNodeType.ACTION,content=line[2:],line_number=idx))
                current_speaker = None
                continue

            # 1. Scene Heading: INT. / EXT. (check first so ### INT. headings are not skipped)
            scene_match = cls.SCENE_REGEX.match(line)
            if scene_match:
                cleaned_slug = re.sub(r"^#{1,6}\s+`?|`?$", "", line).strip()
                ast.append(ASTElement(
                    node_type=ASTNodeType.SCENE_HEADING,
                    content=cleaned_slug,
                    line_number=idx
                ))
                current_speaker = None
                continue

            # 1b. Structural markdown: act banners, chunk headers, notes, dividers.
            #     Emitted as AST nodes so a single parser classifies the whole document.
            if line.startswith("# ") and not line.startswith("### "):
                ast.append(ASTElement(
                    node_type=ASTNodeType.ACT_BANNER,
                    content=line[2:].strip(),
                    line_number=idx
                ))
                current_speaker = None
                continue

            if line.startswith("## ") and not line.startswith("### ") and not line.startswith("## `"):
                ast.append(ASTElement(
                    node_type=ASTNodeType.CHUNK_HEADER,
                    content=line[3:].strip(),
                    line_number=idx
                ))
                current_speaker = None
                continue

            if line.startswith("### "):
                # Malformed heading (not a scene slug): the reader echoes it verbatim,
                # graph analysis ignores it.
                ast.append(ASTElement(
                    node_type=ASTNodeType.LEGACY_HEADING,
                    content=line,
                    line_number=idx
                ))
                current_speaker = None
                continue

            if line.startswith("> "):
                ast.append(ASTElement(
                    node_type=ASTNodeType.NOTE,
                    content=line[2:].strip(),
                    line_number=idx
                ))
                current_speaker = None
                continue

            if line == "---":
                ast.append(ASTElement(
                    node_type=ASTNodeType.DIVIDER,
                    content="",
                    line_number=idx
                ))
                current_speaker = None
                continue

            # Skip fences, metadata banners, and any stray markdown headings
            if (
                line.startswith("#")
                or line.startswith("```")
                or re.match(r"^\*\*(?:format|continuity|prose|version|draft|author|title|standard|style)", line, re.IGNORECASE)
            ):
                current_speaker = None
                continue

            # 1. Markdown-wrapped screenplay cue: **CHARACTER (CONT'D):** *(paren)* "Dialogue"
            #    Any speaker text is accepted (Unicode names, dots for O.S./V.O., slashes
            #    for KNOWN-FORM cues); only '*' and ':' are excluded.
            inline_match = re.match(r"^\*\*([^*:\n]+?):\*\*\s*(.*)$", line)
            if inline_match:
                speaker_raw = inline_match.group(1).strip()
                remainder = inline_match.group(2).strip()

                # Clean speaker: strip (CONT'D) and normalize
                speaker_clean = re.sub(r"\(CONT'D\)", "", speaker_raw, flags=re.IGNORECASE).strip().upper()
                current_speaker = speaker_clean

                ast.append(ASTElement(
                    node_type=ASTNodeType.CHARACTER,
                    content=speaker_raw,
                    speaker=current_speaker,
                    line_number=idx
                ))

                # Check if remainder contains inline parenthetical: *(smug)* "Dialogue"
                paren_match = re.match(r"^(?:\*\((.*?)\)\*|\((.*?)\))\s*(.*)$", remainder)
                if paren_match:
                    paren_text = (paren_match.group(1) or paren_match.group(2) or "").strip()
                    dialogue_text = paren_match.group(3).strip().strip('"')
                    ast.append(ASTElement(
                        node_type=ASTNodeType.PARENTHETICAL,
                        content=f"({paren_text})",
                        speaker=current_speaker,
                        line_number=idx
                    ))
                    if dialogue_text:
                        ast.append(ASTElement(
                            node_type=ASTNodeType.DIALOGUE,
                            content=dialogue_text,
                            speaker=current_speaker,
                            line_number=idx
                        ))
                else:
                    dialogue_text = remainder.strip('"')
                    if dialogue_text:
                        ast.append(ASTElement(
                            node_type=ASTNodeType.DIALOGUE,
                            content=dialogue_text,
                            speaker=current_speaker,
                            line_number=idx
                        ))
                continue

            # A standalone bold cue may omit the colon. Interpret it without
            # rewriting source text; exclude sound effects and prose headings.
            bold_cue = re.fullmatch(r'\*\*([^*:\n]+)\*\*', line)
            if bold_cue and idx < len(lines) and lines[idx].strip():
                name = bold_cue.group(1).strip()
                latin_cue = name.isupper() and any(ch.isalpha() for ch in name)
                cjk_cue = bool(re.fullmatch(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]{1,12}', name))
                if ((latin_cue or cjk_cue) and len(name) < 40 and
                    not any(ch in name for ch in '[]!?—–！？。')):
                    current_speaker = name.upper()
                    ast.append(ASTElement(node_type=ASTNodeType.CHARACTER, content=name,
                                          speaker=current_speaker, line_number=idx))
                    continue

            # 2. Scene Heading: INT. / EXT.
            scene_match = cls.SCENE_REGEX.match(line)
            if scene_match:
                cleaned_slug = re.sub(r"^#{1,6}\s+`?|`?$", "", line).strip()
                ast.append(ASTElement(
                    node_type=ASTNodeType.SCENE_HEADING,
                    content=cleaned_slug,
                    line_number=idx
                ))
                current_speaker = None
                continue

            # 3. Transitions (e.g. CUT TO:, > TITLE:)
            if cls.TRANSITION_REGEX.match(line):
                ast.append(ASTElement(
                    node_type=ASTNodeType.TRANSITION,
                    content=line,
                    line_number=idx
                ))
                current_speaker = None
                continue

            # 4. Standard Fountain Character Cue: ALL CAPS on single line.
            #    Bracketed UI readouts ("[CONTAMINANTS: 0.0%]") and CJK prose that happens
            #    to contain Latin capitals ("...OOTD...") both satisfy str.isupper(), so
            #    they must be excluded explicitly.
            if (
                line.isupper()
                and len(line) < 40
                and not line.endswith(":")
                and not line.startswith("*")
                and ":" not in line
                and "[" not in line
                and "]" not in line
                and not re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", line)
            ):
                speaker_clean = re.sub(r"\(CONT'D\)", "", line, flags=re.IGNORECASE).strip().upper()
                current_speaker = speaker_clean
                ast.append(ASTElement(
                    node_type=ASTNodeType.CHARACTER,
                    content=line,
                    speaker=current_speaker,
                    line_number=idx
                ))
                continue

            # 5. Parenthetical on standalone line: (whispering) or *(whispering)*
            #    Only within a character block; a bare "(...)" elsewhere is a stage direction.
            cleaned_paren = line.strip("*")
            if current_speaker and cls.PAREN_REGEX.match(cleaned_paren):
                ast.append(ASTElement(
                    node_type=ASTNodeType.PARENTHETICAL,
                    content=cleaned_paren,
                    speaker=current_speaker,
                    line_number=idx
                ))
                continue

            # 6. Dialogue Line (follows an active speaker)
            if current_speaker:
                # A leading stage parenthetical is its own node, so style rules can
                # see it and it does not leak into the spoken dialogue text.
                inline_paren = re.match(r"^\((.*?)\)\s*(.*)$", line)
                if inline_paren and inline_paren.group(2).strip():
                    ast.append(ASTElement(
                        node_type=ASTNodeType.PARENTHETICAL,
                        content=f"({inline_paren.group(1).strip()})",
                        speaker=current_speaker,
                        line_number=idx
                    ))
                    line = inline_paren.group(2).strip()
                clean_dialogue = line.strip('"')
                ast.append(ASTElement(
                    node_type=ASTNodeType.DIALOGUE,
                    content=clean_dialogue,
                    speaker=current_speaker,
                    line_number=idx
                ))
                continue

            # 7. Action / Scene Description
            clean_action = line.strip("*")
            ast.append(ASTElement(
                node_type=ASTNodeType.ACTION,
                content=clean_action,
                line_number=idx
            ))
            current_speaker = None

        return ast
