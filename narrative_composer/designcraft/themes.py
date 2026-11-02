"""
DesignCraft Professional Themes & Typographic Styling Specifications.
Provides calibrated color palettes (CMYK process swatches), background layers,
paragraph rules, and typography hierarchies for deluxe screenplay publishing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SwatchDef:
    name: str
    c: float
    m: float
    y: float
    k: float
    color_type: str = "process"

    def to_designcraft(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": {
                "kind": "color",
                "color": {
                    "model": "cmyk",
                    "c": round(self.c, 4),
                    "m": round(self.m, 4),
                    "y": round(self.y, 4),
                    "k": round(self.k, 4),
                },
                "color_type": self.color_type,
            },
            "locked": False,
            "named": True,
            "hidden": False,
        }


@dataclass
class ThemeConfig:
    name: str
    display_name: str
    bg_swatch: str
    swatches: List[SwatchDef]
    style_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    enable_background: bool = True
    enable_scene_rules: bool = True


# Theme 1: Archival Warm Ivory (Criterion Editorial Edition)
# Deep slate scene headers with subtle golden dividing rules on a luxurious warm vellum page.
ARCHIVAL_WARM_IVORY = ThemeConfig(
    name="archival_ivory",
    display_name="Archival Warm Ivory (Criterion Edition)",
    bg_swatch="WarmIvoryBg",
    swatches=[
        # Background: subtle warm cream/vellum
        SwatchDef(name="WarmIvoryBg", c=0.0, m=0.02, y=0.06, k=0.02),
        # Scene Headings: deep rich slate
        SwatchDef(name="SlateSceneHeader", c=0.70, m=0.55, y=0.45, k=0.60),
        # Scene Accent Rule: burnished warm gold
        SwatchDef(name="GoldAccentRule", c=0.10, m=0.30, y=0.80, k=0.10),
        # Character Cues: warm bronze / copper
        SwatchDef(name="BronzeCharacter", c=0.20, m=0.60, y=0.80, k=0.30),
        # Body text & Dialogue: deep rich charcoal
        SwatchDef(name="CharcoalBody", c=0.50, m=0.40, y=0.40, k=0.85),
        # Parentheticals: muted slate / olive gray
        SwatchDef(name="MutedParenthetical", c=0.40, m=0.30, y=0.30, k=0.40),
        # Transitions: dramatic crimson / vermilion
        SwatchDef(name="CrimsonTransition", c=0.15, m=0.95, y=0.85, k=0.10),
    ],
    style_overrides={
        "SceneHeading": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 14.0},
                "fill": "SlateSceneHeader",
                "fillTint": 1.0,
                "tracking": 30.0,
            },
            "para": {
                "spaceBefore": 18.0,
                "spaceAfter": 6.0,
                "keepWithNext": 1,
                "ruleBelow": {
                    "on": True,
                    "weight": 1.25,
                    "color": "GoldAccentRule",
                    "tint": 1.0,
                    "columnWidth": True,
                    "offset": 4.0,
                    "leftIndent": 0.0,
                    "rightIndent": 0.0,
                },
            },
        },
        "Action": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "CharcoalBody",
                "fillTint": 1.0,
                "tracking": 0.0,
            },
            "para": {
                "spaceBefore": 0.0,
                "spaceAfter": 8.0,
            },
        },
        "CharacterCue": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "BronzeCharacter",
                "fillTint": 1.0,
                "tracking": 50.0,
                "capitalization": "allCaps",
            },
            "para": {
                "leftIndent": 144.0,
                "spaceBefore": 12.0,
                "spaceAfter": 0.0,
                "keepWithNext": 1,
            },
        },
        "Parenthetical": {
            "chars": {
                "size": 11.0,
                "leading": {"kind": "points", "value": 12.0},
                "fill": "MutedParenthetical",
                "fillTint": 1.0,
                "tracking": 10.0,
            },
            "para": {
                "leftIndent": 115.0,
                "rightIndent": 115.0,
                "spaceBefore": 0.0,
                "spaceAfter": 0.0,
                "keepWithNext": 1,
            },
        },
        "Dialogue": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "CharcoalBody",
                "fillTint": 1.0,
                "tracking": 0.0,
            },
            "para": {
                "leftIndent": 72.0,
                "rightIndent": 72.0,
                "spaceBefore": 0.0,
                "spaceAfter": 8.0,
            },
        },
        "Transition": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 14.0},
                "fill": "CrimsonTransition",
                "fillTint": 1.0,
                "tracking": 40.0,
                "capitalization": "allCaps",
            },
            "para": {
                "align": "right",
                "spaceBefore": 14.0,
                "spaceAfter": 14.0,
                "keepWithNext": 1,
            },
        },
        "PageHeader": {
            "chars": {
                "size": 10.0,
                "leading": {"kind": "points", "value": 12.0},
                "fill": "SlateSceneHeader",
                "fillTint": 0.8,
                "tracking": 20.0,
            },
            "para": {
                "align": "right",
            },
        },
    },
)


# Theme 2: Midnight Noir (Studio Dark Mode)
# Deep obsidian pages, platinum dialogue, golden character headers, and electric neon accents.
MIDNIGHT_NOIR = ThemeConfig(
    name="midnight_noir",
    display_name="Midnight Noir (Studio Dark Mode)",
    bg_swatch="ObsidianDarkBg",
    swatches=[
        SwatchDef(name="ObsidianDarkBg", c=0.70, m=0.65, y=0.60, k=0.85),
        SwatchDef(name="NoirBannerBg", c=0.60, m=0.50, y=0.45, k=0.75),
        SwatchDef(name="GoldAccent", c=0.10, m=0.25, y=0.80, k=0.05),
        SwatchDef(name="PlatinumDialogue", c=0.05, m=0.04, y=0.04, k=0.08),
        SwatchDef(name="NeonCyan", c=0.80, m=0.10, y=0.10, k=0.0),
        SwatchDef(name="MutedSilver", c=0.20, m=0.15, y=0.15, k=0.20),
    ],
    style_overrides={
        "SceneHeading": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 14.0},
                "fill": "GoldAccent",
                "fillTint": 1.0,
                "tracking": 30.0,
            },
            "para": {
                "spaceBefore": 18.0,
                "spaceAfter": 6.0,
                "keepWithNext": 1,
                "ruleBelow": {
                    "on": True,
                    "weight": 1.25,
                    "color": "GoldAccent",
                    "tint": 1.0,
                    "columnWidth": True,
                    "offset": 4.0,
                    "leftIndent": 0.0,
                    "rightIndent": 0.0,
                },
            },
        },
        "Action": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "PlatinumDialogue",
                "fillTint": 1.0,
                "tracking": 0.0,
            },
            "para": {
                "spaceBefore": 0.0,
                "spaceAfter": 8.0,
            },
        },
        "CharacterCue": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "GoldAccent",
                "fillTint": 1.0,
                "tracking": 50.0,
                "capitalization": "allCaps",
            },
            "para": {
                "leftIndent": 144.0,
                "spaceBefore": 12.0,
                "spaceAfter": 0.0,
                "keepWithNext": 1,
            },
        },
        "Parenthetical": {
            "chars": {
                "size": 11.0,
                "leading": {"kind": "points", "value": 12.0},
                "fill": "MutedSilver",
                "fillTint": 1.0,
                "tracking": 10.0,
            },
            "para": {
                "leftIndent": 115.0,
                "rightIndent": 115.0,
                "spaceBefore": 0.0,
                "spaceAfter": 0.0,
                "keepWithNext": 1,
            },
        },
        "Dialogue": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 13.5},
                "fill": "PlatinumDialogue",
                "fillTint": 1.0,
                "tracking": 0.0,
            },
            "para": {
                "leftIndent": 72.0,
                "rightIndent": 72.0,
                "spaceBefore": 0.0,
                "spaceAfter": 8.0,
            },
        },
        "Transition": {
            "chars": {
                "size": 12.0,
                "leading": {"kind": "points", "value": 14.0},
                "fill": "NeonCyan",
                "fillTint": 1.0,
                "tracking": 40.0,
                "capitalization": "allCaps",
            },
            "para": {
                "align": "right",
                "spaceBefore": 14.0,
                "spaceAfter": 14.0,
                "keepWithNext": 1,
            },
        },
        "PageHeader": {
            "chars": {
                "size": 10.0,
                "leading": {"kind": "points", "value": 12.0},
                "fill": "GoldAccent",
                "fillTint": 0.8,
                "tracking": 20.0,
            },
            "para": {
                "align": "right",
            },
        },
    },
)

AVAILABLE_THEMES: Dict[str, ThemeConfig] = {
    "archival_ivory": ARCHIVAL_WARM_IVORY,
    "midnight_noir": MIDNIGHT_NOIR,
}


def get_theme(name: str) -> ThemeConfig:
    return AVAILABLE_THEMES.get(name, ARCHIVAL_WARM_IVORY)
