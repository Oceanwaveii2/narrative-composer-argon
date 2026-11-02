"""
Entity and State Resolver for Narrative Node Graph (NNG).
Resolves script speaker cues to canonical entity IDs and explicit state slugs
under strict canon filtering without false-positive substring collisions.
"""

from typing import List, Optional, Tuple
import re

from narrative_composer.graph.graph import StoryGraph


class EntityResolver:
    """Resolves character names and cues against an active StoryGraph under canon constraints."""

    def __init__(self, graph: StoryGraph, canon: Optional[str] = None):
        self.graph: StoryGraph = graph
        self.canon: Optional[str] = canon

    def resolve_cue(self, cue: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolves a character cue to (entity_id, state_slug).
        Returns (None, None) if unresolved or invalid under active canon.
        """
        if not cue or not isinstance(cue, str):
            return None, None

        # Clean cue suffixes
        clean = cue.upper().strip()
        for suffix in ["(CONT'D)", "(O.S.)", "(V.O.)"]:
            clean = clean.replace(suffix, "").strip()

        # Step 1: Check state-specific cue_aliases (Exact match)
        for eid, entity in self.graph.entities.items():
            if self.canon and entity.canons and self.canon not in entity.canons:
                continue
            for state in entity.states:
                if state.status != "active":
                    continue
                if self.canon and state.canons and self.canon not in state.canons:
                    continue
                for ca in state.cue_aliases:
                    if self.canon and ca.canons and self.canon not in ca.canons:
                        continue
                    if ca.cue.upper().strip() == clean:
                        return eid, (ca.state or state.slug)

        # Step 2: Check entity-level aliases (Exact match)
        for eid, entity in self.graph.entities.items():
            if self.canon and entity.canons and self.canon not in entity.canons:
                continue
            entity_aliases = [eid.upper(), entity.display_name.upper()] + [a.upper() for a in entity.aliases]
            if clean in entity_aliases:
                return eid, None

        # Step 3: Check longest alias appearing as a whole word in clean cue
        # Exclude relation-modified cues or possessives (e.g. "FRANCINE'S MOM") from resolving to base entity
        relation_words = {"MOM", "MOTHER", "DAD", "FATHER", "FRIEND", "SISTER", "BROTHER", "BOSS", "NANA", "PAPA"}
        cue_tokens = set(re.split(r"[^A-Z0-9]+", clean))
        if not (any(rw in cue_tokens for rw in relation_words) or "'S" in clean or "’S" in clean):
            candidates: List[Tuple[int, str]] = []
            for eid, entity in self.graph.entities.items():
                if self.canon and entity.canons and self.canon not in entity.canons:
                    continue
                all_aliases = [eid.upper(), entity.display_name.upper()] + [a.upper() for a in entity.aliases]
                for alias in all_aliases:
                    pattern = r"(?:\b|_|-)" + re.escape(alias) + r"(?:\b|_|-)"
                    if re.search(pattern, clean):
                        candidates.append((len(alias), eid))

            if candidates:
                # Sort by longest alias match first
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1], None

        return None, None
