"""
Epistemic Context Projector & Prompt Compiler.
Constructs isolated, character-scoped prompts that mathematically purge unobserved global lore.
"""

from __future__ import annotations
from typing import List, Dict, Set, Optional
from ..models.causal_dag import StoryBeatNode
from ..models.epistemic import EpistemicMatrix, EpistemicBelief
from ..models.spatial_fsm import SpatialGraph, ItemLifecycle
from ..models.character import DialecticCharacterNode


class ContextProjector:
    @staticmethod
    def compile_beat_prompt(
        beat: StoryBeatNode,
        epistemic: EpistemicMatrix,
        spatial: SpatialGraph,
        prior_dialogue_tail: str = "",
        character_nodes: Optional[Dict[str, DialecticCharacterNode]] = None
    ) -> str:
        """
        Builds the strict generation contract for an active beat.
        All facts marked UNKNOWN to active characters are purged.
        """
        lines = [
            f"=== SCENE CONTRACT: BEAT {beat.beat_id} (CHUNK {beat.chunk_index}) ===",
            f"SLUGLINE: {beat.slugline}",
            f"ACTIVE CHARACTERS IN ROOM: {', '.join(beat.active_characters)}",
            f"TARGET DRAMATIC GOAL: {beat.dramatic_goal}",
            "",
            "--- PHYSICAL ENVIRONMENT & PROP INVENTORY ---"
        ]

        # Determine the room from the first character (or default to living_room)
        primary_char = beat.active_characters[0] if beat.active_characters else "STELLA"
        char_room = spatial.get_character_room(primary_char)
        if char_room == "UNKNOWN_ROOM":
            char_room = "living_room"

        lines.append(f"CURRENT LOCATION: {char_room.upper()}")

        # Inject only props present in this room or possessed by active characters
        room_props = []
        for item_id, item in spatial.items.items():
            if item.room_id == char_room or (item.held_by and item.held_by.upper() in [c.upper() for c in beat.active_characters]):
                status = f"• {item.name} | Lifecycle: {item.lifecycle.value.upper()}"
                if item.charges_remaining is not None:
                    status += f" (Buttons/Charges remaining: {item.charges_remaining})"
                if item.held_by:
                    status += f" [Held by {item.held_by}]"
                room_props.append(status)

        if room_props:
            lines.extend(room_props)
        else:
            lines.append("• (No active interactive props in this room)")

        lines.extend([
            "",
            "--- CHARACTER SUBJECTIVE BELIEF STATES (THEORY OF MIND) ---"
        ])

        # Project belief state for each active character
        active_embargoes: Set[str] = set()
        for char in beat.active_characters:
            char_upper = char.upper()
            known_facts = epistemic.get_known_facts(char_upper)
            false_beliefs = epistemic.get_false_beliefs(char_upper)

            lines.append(f"[{char_upper} ESTABLISHED KNOWLEDGE]")
            if known_facts:
                for k in known_facts:
                    lines.append(f"  - {k.canonical_text}")
            else:
                lines.append("  - (No knowledge facts have been modeled for this character.)")

            if false_beliefs:
                for fb in false_beliefs:
                    lines.append(f"  - BELIEVES (INCORRECTLY): {fb.canonical_text}")

            # Aggregate embargoes for characters who do not possess facts
            active_embargoes.update(epistemic.get_embargoed_tokens_for_character(char_upper))

        # Inject behavioral directives for active characters only (preserves context budget)
        if character_nodes:
            active_directives = []
            seen_chars: Set[str] = set()
            for char in beat.active_characters:
                char_key = EpistemicMatrix.normalize_character_id(char).lower()
                node = (
                    character_nodes.get(char_key)
                    or character_nodes.get(char.lower())
                    or character_nodes.get(char.upper())
                    or character_nodes.get(char)
                )
                if node and node.character_id not in seen_chars:
                    seen_chars.add(node.character_id)
                    active_directives.append(node.to_prompt_directive(token_budget=120))

            if active_directives:
                lines.extend([
                    "",
                    "--- CHARACTER BEHAVIORAL DIRECTIVES ---",
                    "\n\n".join(active_directives)
                ])

        lines.extend([
            "",
            "--- STRICT NEGATIVE CONSTRAINTS (TOKEN EMBARGOES) ---",
            "The following words/concepts are STRICTLY FORBIDDEN from being spoken by ignorant characters in this beat:",
            f"EMBARGOED TOKENS: {', '.join(sorted(list(active_embargoes))) if active_embargoes else 'None'}",
            "",
            "--- PRECEDING DIALOGUE TAIL (LAST 10 LINES FOR TONAL CONTINUITY) ---",
            prior_dialogue_tail if prior_dialogue_tail else "(Start of scene / No prior dialogue tail)",
            "",
            "--- GENERATION INSTRUCTIONS ---",
            "1. Format: Output ONLY standard Fountain screenplay elements (Scene Heading, Action lines, Character names, Dialogue, Parentheticals). Do not include markdown code fence ticks (```).",
            "2. Follow the author's dramatic goal and the tone of the provided context. Let character action and dialogue serve this particular scene.",
            "3. Avoid turning the goal or context into a list of plot points; use concrete action or dialogue where appropriate.",
            "4. Respect the modeled environment and prop states. Do not invent a required physical gag or personality trait.",
            "5. Zero Lore Leaks: NEVER speak or reveal any embargoed token or unobserved backstory."
        ])

        return "\n".join(lines)


def graph_context_block(
    graph: Any,
    entities: List[str],
    state_slugs: Optional[Any] = None,
    canon: str = "hot_scoomp_main",
    max_chars: int = 1200,
) -> str:
    """
    Assembles joined semantic context for active characters and physical states.
    Returns length-bounded context text for scene projection.
    Guarded with try/except so graph issues can never break generation.
    """
    try:
        from ..graph.enrich import semantic_context

        chunks: List[str] = []
        slug_map: Dict[str, str] = {}
        if isinstance(state_slugs, dict):
            slug_map = state_slugs
        elif isinstance(state_slugs, (list, tuple)):
            for i, ent in enumerate(entities):
                if i < len(state_slugs):
                    slug_map[ent] = state_slugs[i]

        for ent in entities:
            eid = ent.lower().strip()
            slug = slug_map.get(eid) or slug_map.get(ent)
            if slug:
                target_id = slug if slug.startswith(f"{eid}.") else f"{eid}.state.{slug}"
            else:
                target_id = eid

            ctx = semantic_context(
                graph=graph,
                target_id=target_id,
                canon=canon,
                max_chars=max_chars,
            )
            txt = ctx.get("text", "").strip()
            if txt:
                chunks.append(txt)

        joined = "\n\n".join(chunks)
        if len(joined) > max_chars:
            joined = joined[: max_chars - 3].rstrip() + "..."
        return joined
    except Exception as exc:
        import logging
        logging.warning(f"Advisory graph_context_block failed: {exc}")
        return ""

