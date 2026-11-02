"""
Pydantic Data Models for DesignCraft Documents (v0.8.0 specification).
Enforces exact structural invariants for serialization into native .designcraft archives.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DesignCraftBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class Margins(DesignCraftBase):
    top: float = 72.0
    bottom: float = 72.0
    inside: float = 108.0
    outside: float = 72.0


class Columns(DesignCraftBase):
    count: int = 1
    gutter: float = 0.0


class Page(DesignCraftBase):
    id: int
    width: float = 612.0
    height: float = 792.0
    x: float = 0.0
    side: str = "single"
    margins: Margins = Field(default_factory=Margins)
    columns: Columns = Field(default_factory=Columns)
    local_margins: bool = False
    parent: Optional[int] = None
    show_parent_items: bool = True


class SubpathAnchor(DesignCraftBase):
    p: List[float]


class Subpath(DesignCraftBase):
    anchors: List[SubpathAnchor]
    closed: bool = True


class PathData(DesignCraftBase):
    subpaths: List[Subpath]


class TextFrameOptions(DesignCraftBase):
    columns: int = 1
    columns_kind: str = "fixedNumber"
    gutter: float = 0.0
    column_width: float = 0.0
    balance_columns: bool = False
    inset: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    vertical_justification: str = "top"
    vj_paragraph_spacing_limit: float = 0.0
    first_baseline: str = "ascent"
    first_baseline_min: float = 0.0
    ignore_wrap: bool = False
    auto_size: str = "off"
    auto_size_ref: int = 4
    column_rule: bool = False
    column_rule_weight: float = 1.0
    column_rule_color: str = "[Black]"
    column_rule_tint: float = 1.0
    column_rule_offset: float = 0.0
    column_rule_top_inset: float = 0.0
    column_rule_bottom_inset: float = 0.0


class ItemContent(DesignCraftBase):
    type: str = "text"
    story: Optional[int] = None
    options: Optional[TextFrameOptions] = None


def default_corners() -> Dict[str, Any]:
    return {"corners": [{"shape": "none", "size": 0.0} for _ in range(4)]}


def default_effects() -> Dict[str, Any]:
    return {
        "dropShadow": {
            "on": False,
            "color": "[Black]",
            "opacity": 0.75,
            "angle": 120.0,
            "distance": 7.0,
            "size": 5.0,
            "spread": 0.0,
        },
        "feather": 0.0,
    }


class Item(DesignCraftBase):
    id: int
    name: str = ""
    layer: int = 1
    shape: str = "rectangle"
    path: PathData
    xf: List[float] = Field(default_factory=lambda: [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    fill: Dict[str, Any] = Field(default_factory=lambda: {"kind": "none"})
    stroke: Dict[str, Any] = Field(default_factory=lambda: {"kind": "none"})
    corners: Dict[str, Any] = Field(default_factory=default_corners)
    opacity: float = 1.0
    blend: str = "Normal"
    effects: Dict[str, Any] = Field(default_factory=default_effects)
    wrap: Dict[str, Any] = Field(default_factory=lambda: {"mode": "none"})
    locked: bool = False
    hidden: bool = False
    nonprinting: bool = False
    object_style: str = "[Basic Text Frame]"
    content: ItemContent


class Spread(DesignCraftBase):
    id: int
    pages: List[Page]
    items: List[Item] = Field(default_factory=list)
    parent: Optional[Dict[str, Any]] = None
    allow_shuffle: bool = True


class ParaFormat(DesignCraftBase):
    style: str


class CharRun(DesignCraftBase):
    len: int
    style: str = "[None]"


class Story(DesignCraftBase):
    id: int
    text: str
    paras: List[ParaFormat] = Field(default_factory=list)
    chars: List[CharRun] = Field(default_factory=list)
    frames: List[int] = Field(default_factory=list)
    direction: str = "leftToRight"
    vertical: bool = False
    rev: int = 1
    tables: Dict[str, Any] = Field(default_factory=dict)


class Layer(DesignCraftBase):
    id: int = 1
    name: str = "Screenplay Layer"
    color: List[int] = Field(default_factory=lambda: [43, 155, 255])
    visible: bool = True
    locked: bool = False
    printable: bool = True
    show_guides: bool = True
    suppress_wrap_when_hidden: bool = False


class DesignCraftDoc(DesignCraftBase):
    title: str = "Screenplay Document"
    settings: Dict[str, Any]
    spreads: List[Spread]
    parents: List[Any] = Field(default_factory=list)
    layers: List[Layer] = Field(default_factory=lambda: [Layer()])
    stories: Dict[str, Story]
    styles: Dict[str, Any]
    swatches: List[Any]
    endnote_options: Dict[str, Any] = Field(default_factory=dict, alias="endnoteOptions")
    sections: List[Dict[str, Any]] = Field(
        default_factory=lambda: [
            {
                "start": 0,
                "startNumber": 1,
                "style": "arabic",
                "prefix": "",
                "marker": "",
                "includePrefix": False,
            }
        ]
    )
    assets: Dict[str, Any] = Field(default_factory=dict)
    text_variables: List[Any] = Field(default_factory=list, alias="textVariables")
    footnote_options: Dict[str, Any] = Field(default_factory=dict, alias="footnoteOptions")
    xref_formats: List[Any] = Field(default_factory=list, alias="xrefFormats")
    created: int = 1700000000
    modified: int = 1700000000
    next_id: int = 1000
