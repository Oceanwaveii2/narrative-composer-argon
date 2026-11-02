"""
Slugline Parser & Spatial Environment Tokenizer.
Part of Milestone 1: Dynamic Spatial Slugline & Co-Presence Engine.

Parses arbitrary Fountain and Markdown screenplay sluglines into structured
spatial environments, canonical room tokens, and parent location hierarchies.
"""

from __future__ import annotations
import re
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field


class ParsedSlugline(BaseModel):
    raw_text: str = Field(..., description="Original unparsed slugline line")
    clean_text: str = Field(..., description="Clean slugline without markdown markers")
    setting_type: str = Field(..., description="INT, EXT, INT/EXT, or EXT/INT")
    primary_location: str = Field(..., description="Main building, area, or compound")
    secondary_location: Optional[str] = Field(None, description="Specific room or sub-zone")
    time_of_day: Optional[str] = Field(None, description="DAY, NIGHT, CONTINUOUS, etc.")
    canonical_room_id: str = Field(..., description="Normalized room identifier token")
    parent_location_id: Optional[str] = Field(None, description="Normalized parent venue ID")
    aliases: List[str] = Field(default_factory=list, description="Alternative lookup keys for this room")
    is_interior: bool = Field(default=True)
    is_exterior: bool = Field(default=False)


class SluglineParser:
    """
    Robust tokenizer and normalizer for screenplay scene headings.
    Handles standard Fountain formatting as well as markdown-wrapped headings.
    """

    KNOWN_TIMES_OF_DAY = {
        "DAY", "NIGHT", "CONTINUOUS", "SAME", "LATER", "MOMENTS LATER",
        "DAWN", "DUSK", "SUNSET", "SUNRISE", "EVENING", "AFTERNOON", "MORNING"
    }

    # Core domestic rooms mapped to canonical short tokens
    CANONICAL_SHORT_ROOMS = {
        "living room": "living_room",
        "hallway": "hallway",
        "kitchen": "kitchen",
        "bedroom": "upstairs_bedroom",
        "upstairs bedroom": "upstairs_bedroom",
        "cardio cube": "living_room",
        "cube": "living_room",
    }

    @classmethod
    def is_slugline(cls, line: str) -> bool:
        """Determines if a raw text line is a screenplay scene heading."""
        clean = re.sub(r"^(?:###\s+`?|#+\s+|`?)", "", line.strip()).rstrip("`").strip()
        pattern = r"^(INT\.|EXT\.|INT/EXT\.|EXT/INT\.|I/E\.|E/I\.)\s+"
        return bool(re.match(pattern, clean, re.IGNORECASE))

    @classmethod
    def parse(cls, line: str) -> ParsedSlugline:
        """
        Parses a raw slugline into a structured ParsedSlugline object.
        """
        raw = line.strip()
        # 1. Strip markdown artifacts: ### `INT. ...` -> INT. ...
        clean = re.sub(r"^(?:###\s+`?|#+\s+|`?)", "", raw).rstrip("`").strip()

        # 2. Extract Setting Prefix (INT, EXT, etc.)
        setting_match = re.match(r"^(INT\.|EXT\.|INT/EXT\.|EXT/INT\.|I/E\.|E/I\.)\s+(.*)$", clean, re.IGNORECASE)
        if setting_match:
            prefix = setting_match.group(1).upper().rstrip(".")
            remainder = setting_match.group(2).strip()
        else:
            prefix = "INT"
            remainder = clean

        # Normalize prefix
        if prefix in ("I/E", "INT/EXT"):
            setting_type = "INT/EXT"
            is_int, is_ext = True, True
        elif prefix in ("E/I", "EXT/INT"):
            setting_type = "EXT/INT"
            is_int, is_ext = True, True
        elif prefix == "EXT":
            setting_type = "EXT"
            is_int, is_ext = False, True
        else:
            setting_type = "INT"
            is_int, is_ext = True, False

        # 3. Split components by dash variants (em-dash, en-dash, hyphen)
        # Handles " — ", " - ", " – ", " -- "
        parts = [p.strip() for p in re.split(r"\s+[—–-]+\s+", remainder) if p.strip()]

        time_of_day = None
        secondary_loc = None

        if len(parts) >= 3:
            primary_loc = parts[0]
            # Check if last part is time of day
            if parts[-1].upper() in cls.KNOWN_TIMES_OF_DAY or any(t in parts[-1].upper() for t in cls.KNOWN_TIMES_OF_DAY):
                time_of_day = parts[-1].upper()
                secondary_loc = " - ".join(parts[1:-1])
            else:
                secondary_loc = " - ".join(parts[1:])
        elif len(parts) == 2:
            primary_loc = parts[0]
            if parts[1].upper() in cls.KNOWN_TIMES_OF_DAY or any(t in parts[1].upper() for t in cls.KNOWN_TIMES_OF_DAY):
                time_of_day = parts[1].upper()
            else:
                secondary_loc = parts[1]
        elif len(parts) == 1:
            primary_loc = parts[0]
        else:
            primary_loc = "SCENE"

        # 4. Determine Canonical Room ID & Hierarchy
        parent_loc_id = cls.slugify_token(primary_loc)

        # Check for core domestic aliases first
        canonical_room_id = None
        aliases = []

        combined_loc = f"{primary_loc} {secondary_loc or ''}".lower()
        for key, val in cls.CANONICAL_SHORT_ROOMS.items():
            if key in combined_loc:
                canonical_room_id = val
                break

        full_compound_slug = cls.slugify_token(f"{primary_loc} {secondary_loc or ''}".strip())

        if not canonical_room_id:
            canonical_room_id = full_compound_slug
        else:
            # If canonical is short form like living_room, add full compound slug as alias
            if full_compound_slug != canonical_room_id:
                aliases.append(full_compound_slug)

        if parent_loc_id and parent_loc_id not in aliases and parent_loc_id != canonical_room_id:
            aliases.append(parent_loc_id)

        return ParsedSlugline(
            raw_text=raw,
            clean_text=clean,
            setting_type=setting_type,
            primary_location=primary_loc,
            secondary_location=secondary_loc,
            time_of_day=time_of_day,
            canonical_room_id=canonical_room_id,
            parent_location_id=parent_loc_id,
            aliases=aliases,
            is_interior=is_int,
            is_exterior=is_ext,
        )

    @staticmethod
    def slugify_token(text: str) -> str:
        """Converts arbitrary text into a clean snake_case token."""
        s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return s or "room"
