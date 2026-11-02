"""
Spatial Graph & Prop Finite State Machine (FSM) Data Models.
Tracks physical entities, containment, button charges, and lifecycles.
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ItemLifecycle(str, Enum):
    DORMANT = "dormant"           # Resting in environment (e.g., lamp on table)
    EQUIPPED = "equipped"         # Worn on body (e.g., polo, bra, tighty-whities)
    DRAWN = "drawn"               # Held in hand ready for use (e.g., dumbbell)
    DAMAGED = "damaged"           # Partially compromised (e.g., collar popped)
    EXPENDED = "expended"         # Depleted of charges / unfunctional
    DESTROYED = "destroyed"       # Irreversibly broken into shards/pieces
    DEBRIS_HAZARD = "debris_hazard" # Environmental hazard produced by destroyed item


class AnatomicalStage(str, Enum):
    # Hayley stages
    HAYLEY_STANDARD = "hayley_standard"
    HAYLEY_ROGER_DOME = "hayley_roger_dome"
    HAYLEY_BBL_INFLUENCER = "hayley_bbl_influencer"
    # Stella stages
    STELLA_STANDARD = "stella_standard"
    STELLA_NERD_20 = "stella_nerd_20"
    STELLA_NERD_80 = "stella_nerd_80"
    STELLA_BIG_TIDDY_STEVE = "stella_big_tiddy_steve"


class CharacterAnatomy(BaseModel):
    character_id: str
    current_stage: AnatomicalStage = Field(default=AnatomicalStage.STELLA_STANDARD)
    stage_history: List[AnatomicalStage] = Field(default_factory=list)
    active_traits: List[str] = Field(default_factory=list)


class DebrisHazard(BaseModel):
    hazard_id: str = Field(..., description="Unique slug: e.g. 'gloria_lamp_shards'")
    source_item_id: str = Field(..., description="Item that produced this hazard")
    room_id: str = Field(..., description="Room containing the debris")
    material: str = Field(default="ceramic_shards", description="Debris type: ceramic_shards, glass, etc.")
    is_cleared: bool = Field(default=False)
    cleared_by: Optional[str] = None


class BodySlot(str, Enum):
    NONE = "none"
    HEAD = "head"
    TORSO = "torso"
    PELVIS = "pelvis"
    FEET = "feet"
    HAND_LEFT = "hand_left"
    HAND_RIGHT = "hand_right"


class PhysicalEntity(BaseModel):
    item_id: str = Field(..., description="Unique slug: e.g., 'stella_polo_buttons'")
    name: str = Field(..., description="Canonical display name")
    lifecycle: ItemLifecycle = Field(default=ItemLifecycle.DORMANT)
    room_id: str = Field(..., description="Current physical room/zone")
    held_by: Optional[str] = Field(None, description="Character ID if possessed/worn")
    equipped_slot: BodySlot = Field(default=BodySlot.NONE)
    is_visible: bool = Field(default=True)
    charges_remaining: Optional[int] = Field(None, description="Available uses/buttons")
    max_charges: Optional[int] = None
    damage_description: Optional[str] = None

    def pop_charges(self, count: int) -> bool:
        """Decrements charges (e.g. exploding buttons). Returns True if valid, False if over-depleted."""
        if self.charges_remaining is None:
            return True
        if self.charges_remaining < count:
            return False
        self.charges_remaining -= count
        if self.charges_remaining == 0:
            self.lifecycle = ItemLifecycle.EXPENDED
        else:
            self.lifecycle = ItemLifecycle.DAMAGED
        return True

    def shatter(self, description: str = "Shattered into ceramic shards on the floor.") -> bool:
        """Transitions prop to DESTROYED. Returns False if already destroyed."""
        if self.lifecycle == ItemLifecycle.DESTROYED:
            return False
        self.lifecycle = ItemLifecycle.DESTROYED
        self.damage_description = description
        return True


class WitnessRecord(BaseModel):
    """Line-by-line record of an utterance and who physically witnessed it."""
    line_number: int
    speaker: str
    room_id: str
    witnesses: List[str] = Field(default_factory=list)
    text: str


class SpatialGraph(BaseModel):
    items: Dict[str, PhysicalEntity] = Field(default_factory=dict)
    character_locations: Dict[str, str] = Field(default_factory=dict)
    room_topology: Dict[str, List[str]] = Field(default_factory=dict)
    room_aliases: Dict[str, List[str]] = Field(default_factory=dict)
    debris_hazards: Dict[str, DebrisHazard] = Field(default_factory=dict)
    character_anatomies: Dict[str, CharacterAnatomy] = Field(default_factory=dict)
    witness_log: List[WitnessRecord] = Field(default_factory=list)

    def add_debris(
        self,
        hazard_id: str,
        source_item_id: str,
        room_id: str,
        material: str = "ceramic_shards"
    ) -> DebrisHazard:
        """Spawns an active environmental debris hazard in a room."""
        hazard = DebrisHazard(
            hazard_id=hazard_id,
            source_item_id=source_item_id,
            room_id=room_id,
            material=material,
            is_cleared=False
        )
        self.debris_hazards[hazard_id] = hazard
        return hazard

    def clear_debris(self, hazard_id: str, character_id: str) -> bool:
        """Clears an active debris hazard (e.g. swept or cleaned up)."""
        if hazard_id in self.debris_hazards:
            self.debris_hazards[hazard_id].is_cleared = True
            self.debris_hazards[hazard_id].cleared_by = character_id.upper()
            return True
        return False

    def get_active_hazards_in_room(self, room_id: str) -> List[DebrisHazard]:
        """Returns all uncleared debris hazards in a given room (including alias rooms)."""
        hazards = []
        for h in self.debris_hazards.values():
            if not h.is_cleared:
                if h.room_id == room_id:
                    hazards.append(h)
                elif room_id in self.room_aliases.get(h.room_id, []):
                    hazards.append(h)
                elif h.room_id in self.room_aliases.get(room_id, []):
                    hazards.append(h)
        return hazards

    def set_character_stage(
        self,
        character_id: str,
        stage: AnatomicalStage,
        traits: Optional[List[str]] = None
    ) -> CharacterAnatomy:
        """Updates a character's anatomical stage and logs history."""
        char_upper = character_id.upper().strip()
        for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
            char_upper = char_upper.replace(suffix, "").strip()

        if "STELLA" in char_upper or "STEVE" in char_upper:
            char_norm = "STELLA"
        elif "HAYLEY" in char_upper:
            char_norm = "HAYLEY"
        else:
            char_norm = char_upper

        if char_norm not in self.character_anatomies:
            self.character_anatomies[char_norm] = CharacterAnatomy(
                character_id=char_norm,
                current_stage=stage,
                stage_history=[stage],
                active_traits=traits or []
            )
        else:
            anatomy = self.character_anatomies[char_norm]
            anatomy.current_stage = stage
            anatomy.stage_history.append(stage)
            if traits:
                anatomy.active_traits = traits

        return self.character_anatomies[char_norm]

    def get_character_stage(self, character_id: str) -> Optional[AnatomicalStage]:
        """Retrieves a character's active anatomical transformation stage."""
        char_upper = character_id.upper().strip()
        for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
            char_upper = char_upper.replace(suffix, "").strip()

        if "STELLA" in char_upper or "STEVE" in char_upper:
            char_norm = "STELLA"
        elif "HAYLEY" in char_upper:
            char_norm = "HAYLEY"
        else:
            char_norm = char_upper

        anatomy = self.character_anatomies.get(char_norm)
        return anatomy.current_stage if anatomy else None

    def get_character_room(self, character_id: str) -> str:
        clean = character_id.upper().strip()
        for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)", "(PHONE)", "(FILTERED)", "(OFF-SCREEN)", "(VOICE OVER)"]:
            clean = clean.replace(suffix, "").strip()

        if "STELLA" in clean or "STEVE" in clean:
            clean = "STELLA"
        elif "HAYLEY" in clean:
            clean = "HAYLEY"
        elif "HOLLY" in clean:
            clean = "HOLLY"
        elif "FRANCINE" in clean:
            clean = "FRANCINE"
        elif "ROGER" in clean:
            clean = "ROGER"
        elif "RAINEE" in clean:
            clean = "RAINEE"
        elif "RECEPTIONIST" in clean:
            clean = "RECEPTIONIST"
        elif "JEFF" in clean:
            clean = "JEFF"

        return self.character_locations.get(clean, "UNKNOWN_ROOM")

    def is_character_in_room(
        self,
        character_id: str,
        target_room_id: str,
        room_aliases: Optional[List[str]] = None
    ) -> bool:
        """Checks if a character is located in target_room_id or any of its known aliases."""
        current_room = self.get_character_room(character_id)
        if current_room == "UNKNOWN_ROOM":
            return False
        if current_room == target_room_id:
            return True
        if room_aliases and current_room in room_aliases:
            return True
        # Check registered aliases in graph
        known_aliases = self.room_aliases.get(target_room_id, [])
        if current_room in known_aliases:
            return True
        rev_aliases = self.room_aliases.get(current_room, [])
        if target_room_id in rev_aliases:
            return True
        # Check sub-zone containment (e.g. living_room inside ling_eidolessa_house_living_room)
        if target_room_id in current_room or current_room in target_room_id:
            return True
        return False

    def record_utterance(
        self, line_number: int, speaker: str, active_room: str, text: str
    ) -> WitnessRecord:
        """
        Records an utterance and logs all characters present in the active room as witnesses.
        """
        speaker_upper = speaker.upper().replace("(CONT'D)", "").strip()
        # Find all characters currently located in the same room
        present_chars = [
            char_id
            for char_id, room in self.character_locations.items()
            if room == active_room
        ]
        if speaker_upper not in present_chars:
            present_chars.append(speaker_upper)

        rec = WitnessRecord(
            line_number=line_number,
            speaker=speaker_upper,
            room_id=active_room,
            witnesses=present_chars,
            text=text,
        )
        self.witness_log.append(rec)
        return rec

    def was_present_when_spoken(self, listener: str, phrase: str) -> bool:
        """
        Returns True if listener was present in the room when phrase was spoken.
        """
        clean_listener = listener.upper().replace("(CONT'D)", "").strip()
        if "STELLA" in clean_listener or "STEVE" in clean_listener:
            clean_listener = "STELLA"
        elif "HAYLEY" in clean_listener:
            clean_listener = "HAYLEY"
        elif "HOLLY" in clean_listener:
            clean_listener = "HOLLY"
        elif "FRANCINE" in clean_listener:
            clean_listener = "FRANCINE"

        phrase_lower = phrase.lower().strip()

        for rec in self.witness_log:
            if phrase_lower in rec.text.lower():
                # Check if listener was in witnesses list
                norm_witnesses = [self.get_character_room(w) for w in rec.witnesses]
                if clean_listener in rec.witnesses or any(clean_listener in w for w in rec.witnesses):
                    return True
        return False

    def assert_prop_accessible(self, character_id: str, item_id: str) -> bool:
        """Verifies if an item is physically accessible to a character."""
        item = self.items.get(item_id)
        if not item or item.lifecycle == ItemLifecycle.DESTROYED:
            return False
        char_upper = character_id.upper()
        if item.held_by == char_upper:
            return True
        char_room = self.get_character_room(char_upper)
        return item.room_id == char_room

    def move_character(self, character_id: str, new_room_id: str) -> None:
        char_upper = character_id.upper()
        self.character_locations[char_upper] = new_room_id
        # Update any equipped items held by this character
        for item in self.items.values():
            if item.held_by == char_upper:
                item.room_id = new_room_id

    def transfer_item(self, item_id: str, new_holder: Optional[str], new_room_id: Optional[str] = None) -> None:
        item = self.items.get(item_id)
        if not item:
            return
        if new_holder:
            holder_upper = new_holder.upper()
            item.held_by = holder_upper
            item.room_id = self.get_character_room(holder_upper)
        else:
            item.held_by = None
            if new_room_id:
                item.room_id = new_room_id
