"""
Prompt Assembler for the Noir Module 1 Prose Engine.
Synthesizes:
- Prose rewrite request & target span
- Diagnostic findings (filter words to kill, cadence targets)
- Inviolable protected spans and dialogue lines
- Show style profile & voice rules
- Few-shot approved author corrections
- Reference passages from Semantic Drive
into an unambiguous, structured prompt for Gemini 3.8 Flash.
"""

from typing import List
from narrative_composer.prose.approved_edits import ApprovedEditPair
from narrative_composer.prose.models import (
    ProseDiagnosticReport,
    ProseRewriteRequest,
    SpanCategory,
)
from narrative_composer.prose.semantic_drive import ReferencePassage
from narrative_composer.prose.style_engine import StyleProfile


class PromptAssembler:
    """Assembles prompt packets for narrative prose conditioning."""

    @classmethod
    def assemble(
        cls,
        request: ProseRewriteRequest,
        diagnostics: ProseDiagnosticReport,
        style_profile: StyleProfile,
        approved_edits: List[ApprovedEditPair],
        reference_passages: List[ReferencePassage],
        concise_conditioning: bool = False,
    ) -> str:
        sections = []

        # 1. Header & Identity
        sections.append(
            f"=== SYSTEM: NOIR PROSE CONDITIONER ===\n"
            f"SHOW PROFILE: {style_profile.name} (ID: {style_profile.profile_id})\n"
            f"TARGET SPAN ID: {request.target_span_id} (Category: {request.category.value})\n"
            f"TARGET PSYCHIC DISTANCE: Level {request.target_psychic_distance} / 5\n"
            f"TARGET CADENCE BURSTINESS: >= {style_profile.target_cadence_burstiness:.1f}"
        )

        # 2. Inviolable Protected Words & Dialogue
        prot_lines = []
        for span in request.protected_spans:
            if span.category == SpanCategory.DIALOGUE:
                prot_lines.append(f"- CANONICAL DIALOGUE (MUST PRESERVE EXACTLY): \"{span.text}\"")
            else:
                prot_lines.append(
                    f"- PROTECTED TOKENS (CANNOT BE REMOVED/ALTERED): {', '.join(span.required_tokens)}"
                )

        if prot_lines:
            sections.append(
                "=== INVIOLABLE PROTECTED SPANS ===\n"
                "The following words, tokens, and spoken dialogue lines MUST appear intact in the rewritten prose.\n"
                "You are forbidden from mutating, dropping, or replacing them:\n"
                + "\n".join(prot_lines)
            )

        # 3. Active Props & Dramatic Facts
        fact_lines = []
        if request.active_props:
            fact_lines.append("ACTIVE PROPS IN SCENE:")
            for prop, state in request.active_props.items():
                fact_lines.append(f"  * {prop}: {state}")

        if request.character_epistemic_scope:
            fact_lines.append("CHARACTER KNOWLEDGE & SECRETS:")
            for char, facts in request.character_epistemic_scope.items():
                fact_lines.append(f"  * {char} knows: {', '.join(facts)}")

        if request.permitted_facts:
            fact_lines.append("PERMITTED SCENE FACTS:")
            for fact in request.permitted_facts:
                fact_lines.append(f"  * {fact}")

        if fact_lines:
            sections.append("=== DRAMATIC STATE & EPISTEMIC BOUNDARIES ===\n" + "\n".join(fact_lines))

        # 4. Diagnostic Repair Instructions
        repair_items = []
        if diagnostics.filter_word_count > 0:
            repair_items.append(
                f"ELIMINATE FILTER WORDS ({diagnostics.filter_word_count} found: {', '.join(diagnostics.filter_words_found)}). "
                "Do not write 'she noticed' or 'she saw'; depict the physical reaction directly."
            )
        if diagnostics.label_syntax_detected:
            repair_items.append(
                f"FIX EMOTION LABELS ({len(diagnostics.label_examples)} found: {', '.join(diagnostics.label_examples)}). "
                "Show emotion through bodily movement, micro-expressions, and prop interaction."
            )
        if diagnostics.sensory_details_count == 0:
            pref = ", ".join(style_profile.sensory_preferences[:4]) if style_profile.sensory_preferences else "smell, sound, texture"
            if concise_conditioning:
                repair_items.append(
                    f"SENSORY GROUNDING: Add a detail only if it naturally fits the length limit and preserves the facts (e.g. {pref})."
                )
            else:
                repair_items.append(
                    f"INCREASE SENSORY GROUNDING: Add at least one sensory anchor (e.g. {pref})."
                )
        if diagnostics.burstiness_score < 2.0:
            if concise_conditioning:
                repair_items.append("CADENCE: Improve rhythm only where useful; do not add sentences just to vary length.")
            else:
                repair_items.append(
                    "VARY CADENCE: Current sentence lengths are too uniform. Mix short 2-3 word punches with longer clauses."
                )

        if repair_items:
            sections.append("=== DIAGNOSTIC REPAIR INSTRUCTIONS ===\n" + "\n".join(f"[FIX] {r}" for r in repair_items))

        # 5. Show Voice Principles
        voice_lines = [f"- {p}" for p in style_profile.voice_principles]
        if style_profile.banned_cliches:
            voice_lines.append(f"- BANNED CLICHES: {', '.join(style_profile.banned_cliches)}")
        sections.append("=== SHOW VOICE PRINCIPLES ===\n" + "\n".join(voice_lines))

        # 6. Few-Shot Author-Approved Edits (Isolated to this profile)
        if approved_edits:
            edit_lines = []
            for i, edit in enumerate(approved_edits, 1):
                edit_lines.append(
                    f"Example {i} ({edit.defect_type}):\n"
                    f"  DRAFT: \"{edit.original_text}\"\n"
                    f"  APPROVED REWRITE: \"{edit.approved_text}\""
                )
            sections.append("=== FEW-SHOT APPROVED AUTHOR EXAMPLES ===\n" + "\n\n".join(edit_lines))

        # 7. Semantic Reference Passages
        if reference_passages:
            ref_lines = []
            for i, ref in enumerate(reference_passages, 1):
                ref_lines.append(f"Reference {i} [{ref.scene_type}]:\n\"{ref.text}\"")
            sections.append("=== GOLD-STANDARD REFERENCE PASSAGES ===\n" + "\n\n".join(ref_lines))

        # 8. Target Draft & Final Prompt
        sections.append(
            f"=== ORIGINAL DRAFT TEXT TO REWRITE ===\n"
            f"\"{request.original_text}\"\n\n"
            f"Rewrite this draft text following all voice rules, protected words, and diagnostic repairs.\n"
            f"Output ONLY the improved prose text."
        )

        return "\n\n".join(sections)
