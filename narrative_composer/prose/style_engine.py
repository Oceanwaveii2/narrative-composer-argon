"""
Style guide and show voice profiles for the Noir Module 1 Prose Engine.
Provides configurable voice principles, cadence targets, sensory preferences,
and formatting rules for different narrative worlds.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from narrative_composer.prose.ports import StyleProfileRepositoryPort


class StyleProfile(BaseModel):
    """Configuration defining the voice, rhythm, and sensory standards of a show or project."""
    profile_id: str
    name: str
    description: str
    target_cadence_burstiness: float = 4.5
    target_psychic_distance: int = 2
    voice_principles: List[str] = Field(default_factory=list)
    banned_cliches: List[str] = Field(default_factory=list)
    sensory_preferences: List[str] = Field(default_factory=list)
    formatting_rules: List[str] = Field(default_factory=list)


# ============================================================================
# Built-in Standard Profiles
# ============================================================================

HOT_SCOOMP_TV14 = StyleProfile(
    profile_id="hot_scoomp_tv14",
    name="American Dad - Hot Scoomp TV-14",
    description="High-energy animated sitcom prose with sharp comedic dialogue, physical prop absurdity, and vivid sensory contrasts.",
    target_cadence_burstiness=5.0,
    target_psychic_distance=2,
    voice_principles=[
        "Rapid dialogue punches with immediate physiological reactions.",
        "Physical prop comedy: props are volatile, fragile, or exaggerated (e.g. Gloria the flamingo lamp).",
        "Sensory contrast: mix glamorous aesthetics with absurd industrial details (e.g. Sephora powder vs motor oil).",
        "Zero observer filter words: show character realization through posture, glances, and immediate action.",
        "Strict TV-14 boundaries: comedic absurdity, cartoonish physics, sharp satire without gratuitous explicit content.",
    ],
    banned_cliches=[
        "she noticed that",
        "he felt a wave of",
        "said angrily",
        "suddenly without warning",
        "smiled a wicked smile",
    ],
    sensory_preferences=[
        "ozone", "lavender", "coconut oil", "pennzoil", "flax", "chia", "neon tie-dye",
        "velvet", "glossy blowout", "white sparks", "shattering ceramic",
    ],
    formatting_rules=[
        "Preserve canonical dialogue inside standard quotation marks.",
        "Use short, percussive action beats to punctuate dialogue.",
        "Keep blocking concrete: note exact positions of props and room boundaries.",
    ],
)

NOIR_DETECTIVE = StyleProfile(
    profile_id="noir_detective",
    name="Hard-Boiled Noir Detective",
    description="Atmospheric, terse, shadow-drenched hard-boiled mystery.",
    target_cadence_burstiness=3.8,
    target_psychic_distance=1,
    voice_principles=[
        "Visceral first/close-third perspective grounded in physical grit.",
        "Heavy atmospheric contrast: rain, neon through blinds, cigarette smoke, cheap gin.",
        "Cynical, razor-edged observations without emotional melodrama.",
    ],
    banned_cliches=[
        "she seemed to be",
        "he wondered if",
        "replied defensively",
        "little did he know",
    ],
    sensory_preferences=[
        "damp wool", "cheap bourbon", "burnt coffee", "stale tobacco", "wet asphalt", "humming neon",
    ],
    formatting_rules=[
        "Short declarative sentences punctuated by sensory metaphors.",
    ],
)

STANDARD_DRAMATIC = StyleProfile(
    profile_id="standard_dramatic",
    name="Standard Balanced Dramatic Prose",
    description="Balanced third-person prose suitable for general dramatic fiction.",
    target_cadence_burstiness=4.0,
    target_psychic_distance=2,
    voice_principles=[
        "Balanced sentence variety and rhythmic cadence.",
        "Show emotion through physical blocking and concrete sensory details.",
    ],
    banned_cliches=[
        "she noticed", "he felt", "said sadly",
    ],
    sensory_preferences=[],
    formatting_rules=[],
)


# ============================================================================
# Style Profile Repository
# ============================================================================

class StyleProfileRepository(StyleProfileRepositoryPort):
    """In-memory repository for looking up and registering show style profiles."""

    def __init__(self):
        self._profiles: Dict[str, StyleProfile] = {}
        # Pre-populate with built-in profiles
        self.register_profile(HOT_SCOOMP_TV14)
        self.register_profile(NOIR_DETECTIVE)
        self.register_profile(STANDARD_DRAMATIC)

    def register_profile(self, profile: StyleProfile) -> None:
        self._profiles[profile.profile_id] = profile

    def get_style_profile(self, profile_id: str) -> Optional[StyleProfile]:
        return self._profiles.get(profile_id)

    def list_profiles(self) -> List[str]:
        return list(self._profiles.keys())
