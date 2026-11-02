"""
Bridge connecting the upstream Neurosymbolic Narrative Composer to the Noir Module 1 Prose Engine.
Translates screenplay AST elements, Causal DAG story beats, SpatialGraph prop states,
and EpistemicMatrix knowledge into typed ProseRewriteRequests.
"""

import re
import uuid
from typing import Dict, List, Optional
from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType
from narrative_composer.models.causal_dag import StoryBeatNode
from narrative_composer.models.epistemic import EpistemicMatrix
from narrative_composer.models.spatial_fsm import SpatialGraph
from narrative_composer.prose.models import (
    ProtectedSpan,
    ProseRewriteRequest,
    SpanCategory,
)


class ComposerBridgeAdapter:
    """Adapts upstream screenplay AST and symbolic state machines into prose requests."""

    KNOWN_CHARACTERS = [
        "Hayley", "Stella", "Francine", "Holly Graham", "Stan", "Steve", "Roger",
        "Klaus", "Jeff", "Danuta", "Zooey", "Kristen", "Toshi", "Snot"
    ]

    KNOWN_PROPS = [
        "Gloria", "flamingo lamp", "Sephora powder", "itching powder", "tie-dye shorts",
        "resistance bands", "HG smoothie", "dumbbell", "yard plaque", "Yard of the Month"
    ]

    @classmethod
    def extract_protected_spans_from_ast(
        cls,
        elements: List[ASTElement],
    ) -> List[ProtectedSpan]:
        """
        Extracts protected dialogue and protected proper entity spans from surrounding AST elements.
        """
        spans: List[ProtectedSpan] = []

        # 1. Spoken dialogue lines are strictly protected
        for elem in elements:
            if elem.node_type == ASTNodeType.DIALOGUE:
                clean_dialogue = elem.content.strip().strip('"')
                if clean_dialogue:
                    spans.append(
                        ProtectedSpan(
                            span_id=f"dial_{uuid.uuid4().hex[:8]}",
                            category=SpanCategory.DIALOGUE,
                            text=clean_dialogue,
                        )
                    )

        # 2. Extract character names mentioned in the text as protected entity tokens
        combined_text = " ".join(e.content for e in elements)
        matched_characters = [
            char for char in cls.KNOWN_CHARACTERS
            if re.search(rf"\b{re.escape(char)}\b", combined_text, flags=re.IGNORECASE)
        ]
        if matched_characters:
            spans.append(
                ProtectedSpan(
                    span_id=f"prot_chars_{uuid.uuid4().hex[:8]}",
                    category=SpanCategory.GENERAL,
                    text=" ".join(matched_characters),
                    required_tokens=matched_characters,
                )
            )

        # 3. Extract key physical props mentioned
        matched_props = [
            prop for prop in cls.KNOWN_PROPS
            if re.search(rf"\b{re.escape(prop)}\b", combined_text, flags=re.IGNORECASE)
        ]
        if matched_props:
            spans.append(
                ProtectedSpan(
                    span_id=f"prot_props_{uuid.uuid4().hex[:8]}",
                    category=SpanCategory.GENERAL,
                    text=" ".join(matched_props),
                    required_tokens=matched_props,
                )
            )

        return spans

    @classmethod
    def build_request_from_action_element(
        cls,
        action_element: ASTElement,
        project_id: str = "hot_scoomp",
        document_id: str = "act1",
        base_revision: int = 0,
        target_span_id: Optional[str] = None,
        active_room: str = "living_room",
        spatial_graph: Optional[SpatialGraph] = None,
        epistemic_matrix: Optional[EpistemicMatrix] = None,
        surrounding_elements: Optional[List[ASTElement]] = None,
        style_profile_id: str = "standard_dramatic",
    ) -> ProseRewriteRequest:
        """
        Converts a screenplay action AST element into a complete ProseRewriteRequest.
        """
        span_id = target_span_id or f"action_L{action_element.line_number}"
        context_elements = (surrounding_elements or []) + [action_element]

        # 1. Build protected spans
        protected_spans = cls.extract_protected_spans_from_ast(context_elements)

        # 2. Extract active props from SpatialGraph
        active_props: Dict[str, str] = {}
        if spatial_graph:
            for item_name, item in spatial_graph.items.items():
                if item.room_id == active_room or active_room in item.room_id:
                    active_props[item_name] = item.lifecycle.value

        # 3. Extract character knowledge from EpistemicMatrix
        epistemic_scope: Dict[str, List[str]] = {}
        if epistemic_matrix:
            for char_key, char_beliefs in epistemic_matrix.beliefs.items():
                if char_beliefs:
                    display_name = char_key.capitalize()
                    facts = [
                        f"{fact}:{b.name if hasattr(b, 'name') else str(b)}"
                        for fact, b in char_beliefs.items()
                    ]
                    epistemic_scope[display_name] = facts

        return ProseRewriteRequest(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            document_id=document_id,
            base_revision=base_revision,
            target_span_id=span_id,
            original_text=action_element.content,
            category=SpanCategory.STAGE_ACTION,
            protected_spans=protected_spans,
            active_props=active_props,
            character_epistemic_scope=epistemic_scope,
            style_profile_id=style_profile_id,
        )

    @classmethod
    def build_request_from_story_beat(
        cls,
        beat: StoryBeatNode,
        project_id: str = "hot_scoomp",
        document_id: str = "act1",
        base_revision: int = 0,
        active_room: str = "living_room",
        spatial_graph: Optional[SpatialGraph] = None,
        epistemic_matrix: Optional[EpistemicMatrix] = None,
        style_profile_id: str = "standard_dramatic",
    ) -> ProseRewriteRequest:
        """
        Converts an upstream Causal DAG StoryBeatNode into a ProseRewriteRequest.
        """
        active_props: Dict[str, str] = {}
        if spatial_graph:
            for item_name, item in spatial_graph.items.items():
                active_props[item_name] = item.lifecycle.value

        epistemic_scope: Dict[str, List[str]] = {}
        if epistemic_matrix:
            for char in beat.active_characters:
                char_key = epistemic_matrix.normalize_character_id(char)
                beliefs = epistemic_matrix.beliefs.get(char_key, {})
                epistemic_scope[char] = [
                    f"{k}:{v.name if hasattr(v, 'name') else str(v)}"
                    for k, v in beliefs.items()
                ]

        # Protect character names present in the beat
        protected_spans = [
            ProtectedSpan(
                span_id=f"prot_beat_chars_{beat.beat_id}",
                category=SpanCategory.GENERAL,
                text=" ".join(beat.active_characters),
                required_tokens=beat.active_characters,
            )
        ]

        return ProseRewriteRequest(
            request_id=f"req_beat_{beat.beat_id}",
            project_id=project_id,
            document_id=document_id,
            base_revision=base_revision,
            target_span_id=beat.beat_id,
            original_text=beat.dramatic_intent,
            category=SpanCategory.STAGE_ACTION,
            protected_spans=protected_spans,
            permitted_facts=beat.permitted_factual_assertions,
            active_props=active_props,
            character_epistemic_scope=epistemic_scope,
            style_profile_id=style_profile_id,
        )
