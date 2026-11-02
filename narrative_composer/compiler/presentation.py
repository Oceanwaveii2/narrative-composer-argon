"""
Presentation helpers shared by the reader renderer and the legacy compiler.

Kept in a leaf module so both renderers can use it without an import cycle.
"""

from __future__ import annotations
import re
from typing import Optional


def get_character_transformation_pill(speaker: str) -> Optional[str]:
    """Returns a transformation-state badge for cues that imply a character form."""
    sp = speaker.upper().strip()
    for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
        sp = sp.replace(suffix, "").strip()
    # Match whole cue tokens, never substrings: "BOB"/"DEBORAH"/"NOBODY" are not "BO",
    # and "STEVEN" is not "STEVE".
    tokens = set(re.findall(r"[A-Z]+", sp))

    if "BIG TIDDY" in sp or "STEVE" in tokens:
        return '<div class="flex justify-center mb-1"><span class="px-2.5 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full text-[11px] font-mono uppercase tracking-wider font-bold">🚀 Transformation State: Big Tiddy Steve / Nerdy Persona</span></div>'
    if "RAINEE/" in sp or tokens & {"MADONNA", "CHRISTIE", "HEATHER", "KIM", "DEBBIE", "BO"}:
        return '<div class="flex justify-center mb-1"><span class="px-2.5 py-0.5 bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded-full text-[11px] font-mono uppercase tracking-wider font-bold">🪩 Shapeshift State: Rainee Strip Tease</span></div>'
    if "PETER" in tokens:
        return '<div class="flex justify-center mb-1"><span class="px-2.5 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-full text-[11px] font-mono uppercase tracking-wider font-bold">🍻 Transformation State: Peter-Rainee Persona</span></div>'
    if "NURSE" in tokens:
        return '<div class="flex justify-center mb-1"><span class="px-2.5 py-0.5 bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-full text-[11px] font-mono uppercase tracking-wider font-bold">🩺 Transformation State: Nurse Francine Deluxe</span></div>'
    if "HAYLEY FITNESS GODDESS" in sp or "BBL HAYLEY" in sp:
        return '<div class="flex justify-center mb-1"><span class="px-2.5 py-0.5 bg-fuchsia-500/20 text-fuchsia-300 border border-fuchsia-500/40 rounded-full text-[11px] font-mono uppercase tracking-wider font-bold">🍑 Transformation State: Big Booty BBL Influencer</span></div>'
    return None
