"""
AST node definitions for screenplay representation (Fountain compatible).
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ASTNodeType(str, Enum):
    SCENE_HEADING = "scene_heading"
    ACTION = "action"
    CHARACTER = "character"
    PARENTHETICAL = "parenthetical"
    DIALOGUE = "dialogue"
    TRANSITION = "transition"
    # Structural markdown that the reader renders as chrome. Graph analysis ignores these.
    ACT_BANNER = "act_banner"
    CHUNK_HEADER = "chunk_header"
    NOTE = "note"
    DIVIDER = "divider"
    # A '###' line that is not a scene slug (e.g. '### TRANSFORMATION ONE: MADONNA').
    # The reader has always echoed these verbatim as action text; the graph ignores them.
    LEGACY_HEADING = "legacy_heading"


class ASTElement(BaseModel):
    node_type: ASTNodeType = Field(..., description="Screenplay syntactic element type")
    content: str = Field(..., description="Raw textual content of the element")
    speaker: Optional[str] = Field(None, description="Character identifier if applicable (in uppercase)")
    line_number: int = Field(default=0, description="1-indexed line number in source text")

    def __str__(self) -> str:
        if self.node_type == ASTNodeType.CHARACTER:
            return f"**{self.content}**"
        elif self.node_type == ASTNodeType.PARENTHETICAL:
            return f"*({self.content.strip('()')})*"
        elif self.node_type == ASTNodeType.DIALOGUE:
            return f'"{self.content}"'
        elif self.node_type == ASTNodeType.SCENE_HEADING:
            return f"### `{self.content}`"
        return self.content
