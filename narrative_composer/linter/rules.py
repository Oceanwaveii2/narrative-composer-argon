"""
Screenplay Linter Rule Engine & Invariant Checks.
Defines deterministic checks for token embargoes, prop FSM lifecycles, phantom citations, and room presence.
"""

from __future__ import annotations
import re
from typing import List, Optional, Set
from pydantic import BaseModel, Field

from ..models.ast_nodes import ASTElement, ASTNodeType
from ..models.epistemic import EpistemicMatrix, EpistemicBelief
from ..models.spatial_fsm import SpatialGraph, ItemLifecycle


class LintViolation(BaseModel):
    rule_id: str = Field(..., description="Unique invariant rule identifier")
    line_number: int = Field(..., description="Line number of violation")
    speaker: Optional[str] = Field(None, description="Character who spoke or acted")
    offending_text: str = Field(..., description="The exact text snippet that failed")
    diagnostic_message: str = Field(..., description="Detailed explanation of why this is a continuity bug")
    repair_instruction: str = Field(..., description="Actionable instruction to resolve the violation")
    severity: str = Field(default="ERROR", description="'ERROR' (hard failure) or 'WARNING'")


class LinterRuleEngine:
    @staticmethod
    def check_token_embargo(
        node: ASTElement,
        epistemic: EpistemicMatrix
    ) -> Optional[LintViolation]:
        """Rule 1: Detects forbidden tokens uttered by characters who do not possess the fact."""
        if node.node_type != ASTNodeType.DIALOGUE or not node.speaker:
            return None

        speaker = node.speaker.upper()
        forbidden_tokens = epistemic.get_embargoed_tokens_for_character(speaker)
        text_lower = node.content.lower()

        for token in forbidden_tokens:
            pattern = r'\b' + re.escape(token.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return LintViolation(
                    rule_id="RULE_1_FORBIDDEN_TOKEN_EMBARGO",
                    line_number=node.line_number,
                    speaker=speaker,
                    offending_text=node.content,
                    diagnostic_message=f"Character '{speaker}' uttered embargoed token '{token}'. Character has not learned this fact.",
                    repair_instruction=f"Remove or replace '{token}'. Express the line without using this unrevealed concept."
                )
        return None

    @staticmethod
    def check_zombie_prop(
        node: ASTElement,
        spatial: SpatialGraph
    ) -> Optional[LintViolation]:
        """Rule 2: Detects interacting with destroyed, missing, or depleted props."""
        text_lower = node.content.lower()

        for item_id, item in spatial.items.items():
            name_lower = item.name.lower()

            # Check for destroying an already destroyed item
            if item.lifecycle == ItemLifecycle.DESTROYED:
                if name_lower in text_lower or (item_id == "gloria_lamp" and "gloria" in text_lower):
                    # Active destruction verbs (excluding passive descriptions like "shattered corpse" or "shards")
                    if any(v in text_lower for v in ["shatters across", "breaks into", "smashes into", "knocks over the lamp", "teeters and shatters"]):
                        return LintViolation(
                            rule_id="RULE_2A_ZOMBIE_PROP_DESTRUCTION",
                            line_number=node.line_number,
                            speaker=node.speaker,
                            offending_text=node.content,
                            diagnostic_message=f"Attempted to destroy '{item.name}', but item lifecycle is already DESTROYED.",
                            repair_instruction=f"'{item.name}' is already broken in shards on the floor. Reference the existing shards instead of breaking it again."
                        )

            # Check for button over-depletion
            if item.charges_remaining is not None and item.charges_remaining <= 0:
                if item_id == "stella_polo_buttons" or "button" in name_lower:
                    if any(v in text_lower for v in ["button pops", "buttons pop", "button explodes", "buttons explode", "buttons rip off", "button pings"]):
                        return LintViolation(
                            rule_id="RULE_2B_PROP_OVER_DEPLETION",
                            line_number=node.line_number,
                            speaker=node.speaker,
                            offending_text=node.content,
                            diagnostic_message=f"Buttons popped, but '{item.name}' charges_remaining is {item.charges_remaining}.",
                            repair_instruction="All buttons have already popped in previous beats. Do not pop additional buttons; describe the torn fabric or straining bra instead."
                        )
        return None

    @staticmethod
    def check_phantom_citation(
        node: ASTElement,
        prior_committed_script: str
    ) -> Optional[LintViolation]:
        """Rule 3: Catches characters quoting dialogue or blogs that were never committed."""
        if node.node_type != ASTNodeType.DIALOGUE:
            return None

        # Look for explicit quote patterns: You said '...', You called my blog '...', etc.
        matches = re.findall(
            r"(?:you\s+(?:said|called|commented|wrote|referred to)[^'\"]*?)\s*['\"]([^'\"]+)['\"]",
            node.content,
            re.IGNORECASE
        )
        for quoted_snippet in matches:
            clean_snippet = quoted_snippet.strip().rstrip(".,!?;:")
            if len(clean_snippet) > 4:
                if clean_snippet.lower() not in prior_committed_script.lower():
                    return LintViolation(
                        rule_id="RULE_3_PHANTOM_DIALOGUE_CITATION",
                        line_number=node.line_number,
                        speaker=node.speaker,
                        offending_text=node.content,
                        diagnostic_message=f"Character quoted '{clean_snippet}', but this phrase does not exist in prior committed text.",
                        repair_instruction=f"Either plant '{clean_snippet}' in an earlier beat or paraphrase the dialogue without quoting an unsaid line."
                    )
        return None

    @staticmethod
    def check_double_discovery(
        node: ASTElement,
        discovered_entities: Set[str]
    ) -> Optional[LintViolation]:
        """Rule 4: Prevents characters from experiencing an initial visual discovery twice."""
        if node.node_type != ASTNodeType.DIALOGUE or not node.speaker:
            return None

        text_lower = node.content.lower()
        discovery_patterns = [
            (r"(?:are those|is that|what are|look at (?:those|that))\s+(?:little\s+)?([a-z0-9_\s]+)\?", "rocket_ships"),
        ]

        for pattern, entity_key in discovery_patterns:
            if re.search(pattern, text_lower) and "rocket" in text_lower:
                if entity_key in discovered_entities:
                    return LintViolation(
                        rule_id="RULE_4_DOUBLE_DISCOVERY",
                        line_number=node.line_number,
                        speaker=node.speaker,
                        offending_text=node.content,
                        diagnostic_message=f"Character asked an initial discovery question about '{entity_key}', but this feature was already discovered.",
                        repair_instruction=f"Do not act surprised or ask 'Are those {entity_key}?'. Refer to it as an established, already-observed condition."
                    )
        return None

    @staticmethod
    def check_speaker_room_presence(
        node: ASTElement,
        active_room_id: str,
        spatial: SpatialGraph
    ) -> Optional[LintViolation]:
        """Rule 5: Verifies that a character speaking dialogue is physically located in the active room."""
        if node.node_type != ASTNodeType.DIALOGUE or not node.speaker:
            return None

        speaker = node.speaker.upper()
        # O.S. (Off-Screen), V.O. (Voice-Over), PHONE, FILTERED are exempt from strict line-of-sight presence
        exempt_tokens = ["(O.S.)", "(V.O.)", "(PHONE)", "(FILTERED)", "(OFF-SCREEN)", "(VOICE OVER)"]
        if any(tok in speaker for tok in exempt_tokens):
            return None

        char_room = spatial.get_character_room(speaker)
        if char_room != "UNKNOWN_ROOM" and not spatial.is_character_in_room(speaker, active_room_id):
            return LintViolation(
                rule_id="RULE_5_SPEAKER_ABSENT_FROM_ROOM",
                line_number=node.line_number,
                speaker=speaker,
                offending_text=node.content,
                diagnostic_message=f"Character '{speaker}' spoke in room '{active_room_id}', but their physical location is '{char_room}'.",
                repair_instruction=f"Move '{speaker}' into '{active_room_id}' with an action line or mark their dialogue as (O.S.)."
            )
        return None

    @staticmethod
    def check_prop_accessibility(
        node: ASTElement,
        spatial: SpatialGraph
    ) -> Optional[LintViolation]:
        """Rule 6: Verifies that props physically interacted with are accessible in the room."""
        if node.node_type != ASTNodeType.ACTION or not node.speaker:
            return None

        # Check action lines where character manipulates an item
        speaker = node.speaker.upper()
        text_lower = node.content.lower()

        for item_id, item in spatial.items.items():
            name_lower = item.name.lower()
            if name_lower in text_lower and any(v in text_lower for v in ["picks up", "grabs", "takes", "holds", "draws"]):
                if not spatial.assert_prop_accessible(speaker, item_id):
                    return LintViolation(
                        rule_id="RULE_6_PROP_INACCESSIBLE",
                        line_number=node.line_number,
                        speaker=speaker,
                        offending_text=node.content,
                        diagnostic_message=f"Character '{speaker}' attempted to interact with '{item.name}', but item is in room '{item.room_id}' while character is in '{spatial.get_character_room(speaker)}'.",
                        repair_instruction=f"Move '{item.name}' into the active room before '{speaker}' interacts with it."
                    )
        return None

    @staticmethod
    def check_debris_hazard_safety(
        node: ASTElement,
        active_room_id: str,
        spatial: SpatialGraph
    ) -> Optional[LintViolation]:
        """
        Rule 7: Verifies physical interaction with rooms containing active sharp debris hazards.
        Flags action lines where characters walk barefoot across floors with uncleared shards
        without acknowledging, stepping around, or clearing the hazard.
        """
        if node.node_type != ASTNodeType.ACTION:
            return None

        hazards = spatial.get_active_hazards_in_room(active_room_id)
        if not hazards:
            return None

        text_lower = node.content.lower()

        # Check if action describes barefoot walking
        barefoot_triggers = ["barefoot", "in socks", "shoeless", "without shoes", "unshod"]
        is_barefoot = any(b in text_lower for b in barefoot_triggers)

        # Check if text acknowledges or handles the debris
        acknowledges_debris = any(w in text_lower for w in [
            "shards", "debris", "ceramic shards", "broken glass", "sweeps", "tiptoes",
            "careful where", "avoids the", "steps over", "clears the"
        ])

        if is_barefoot and not acknowledges_debris:
            hazard_names = ", ".join(f"{h.hazard_id} ({h.material})" for h in hazards)
            return LintViolation(
                rule_id="RULE_7_DEBRIS_HAZARD_SAFETY",
                line_number=node.line_number,
                speaker=node.speaker,
                offending_text=node.content,
                diagnostic_message=f"Action line describes barefoot movement in room '{active_room_id}', which contains active sharp debris hazards ({hazard_names}) without acknowledging or avoiding the hazard.",
                repair_instruction="Acknowledge the ceramic/glass shards on the floor, step carefully around the debris, or wear footwear.",
                severity="ERROR"
            )
        return None

    @staticmethod
    def check_transformation_persona_consistency(
        node: ASTElement,
        spatial: SpatialGraph
    ) -> Optional[LintViolation]:
        """
        Rule 8: Enforces behavioral, dialogue, and mannerism consistency for transformed characters.
        - Stella as Big Tiddy Steve: Must not deliver cool/aloof teen lines; must exhibit nerd mannerisms/whines.
        - Hayley as BBL Influencer: Must not deliver high-minded serious investigative journalism lectures.
        """
        if node.node_type not in (ASTNodeType.DIALOGUE, ASTNodeType.ACTION):
            return None

        text_lower = node.content.lower()
        speaker = (node.speaker or "").upper()
        norm_speaker = EpistemicMatrix.normalize_character_id(speaker)

        active_stage = spatial.get_character_stage(norm_speaker)
        if not active_stage:
            return None

        stage_val = active_stage.value if hasattr(active_stage, "value") else str(active_stage)

        # Check Stella as Big Tiddy Steve
        if norm_speaker == "STELLA" and stage_val == "stella_big_tiddy_steve":
            if node.node_type == ASTNodeType.DIALOGUE:
                aloof_markers = [
                    "i'm way too cool for this",
                    "as a popular girl",
                    "my high school cheer",
                    "you're such a dork",
                ]
                for m in aloof_markers:
                    if m in text_lower:
                        return LintViolation(
                            rule_id="RULE_8_ANATOMICAL_PERSONA_MISMATCH",
                            line_number=node.line_number,
                            speaker=node.speaker,
                            offending_text=node.content,
                            diagnostic_message=f"Character 'STELLA' is in 'STELLA_BIG_TIDDY_STEVE' stage but delivered aloof teen dialogue: '{m}'.",
                            repair_instruction="Align dialogue with the Steve persona: whiny cadence, math/geometry obsession, PB&J fixation, or nerd insecurity.",
                            severity="ERROR"
                        )

        # Check Hayley as BBL Influencer
        if norm_speaker == "HAYLEY" and stage_val == "hayley_bbl_influencer":
            if node.node_type == ASTNodeType.DIALOGUE:
                serious_journalism_markers = [
                    "i am an investigative reporter writing a major exposé",
                    "capitalism must be dismantled through serious journalism",
                    "my pulitzer-worthy investigative report",
                ]
                for m in serious_journalism_markers:
                    if m in text_lower:
                        return LintViolation(
                            rule_id="RULE_8_ANATOMICAL_PERSONA_MISMATCH",
                            line_number=node.line_number,
                            speaker=node.speaker,
                            offending_text=node.content,
                            diagnostic_message=f"Character 'HAYLEY' is in 'HAYLEY_BBL_INFLUENCER' stage but delivered serious investigative reporter monologue: '{m}'.",
                            repair_instruction="Reflect active BBL Influencer persona: vocal fry, booty clap pride, superficial glamour, or vanity drawl.",
                            severity="ERROR"
                        )

        return None

    @staticmethod
    def check_source_name_embargo(
        node: ASTElement,
        custom_banned_tokens: Optional[Set[str]] = None,
    ) -> Optional[LintViolation]:
        """Rule 9: Detects forbidden source namedrops (Kardashian, Boondocks, Scoomp) and bad AI mining tropes."""
        # Only in-story text counts: document chrome (act banners, chunk headers, notes,
        # malformed '###' headings) legitimately names the source in its title.
        if node.node_type not in (
            ASTNodeType.ACTION,
            ASTNodeType.DIALOGUE,
            ASTNodeType.PARENTHETICAL,
        ):
            return None

        banned = custom_banned_tokens or {
            "kardashian",
            "kardashians",
            "boondocks",
            "scoomp",
            "hot scoomp",
            "fake cakes",
            "flat-to-fat",
            "augmentation addiction",
        }
        text_lower = node.content.lower()

        for token in banned:
            pattern = rf"\b{re.escape(token)}\b"
            if re.search(pattern, text_lower):
                return LintViolation(
                    rule_id="RULE_9_SOURCE_NAME_EMBARGO",
                    line_number=node.line_number,
                    speaker=node.speaker,
                    offending_text=node.content,
                    diagnostic_message=f"Leaked forbidden real-world source token '{token}'. The script must not break the 4th wall or recite source titles.",
                    repair_instruction=f"Remove '{token}' and describe the physical behavior or in-universe dialogue instead.",
                    severity="ERROR",
                )
        return None

    @staticmethod
    def check_telepathic_phrase_leak(
        node: ASTElement,
        spatial: SpatialGraph,
        coined_phrases: Optional[Dict[str, str]] = None,
    ) -> Optional[LintViolation]:
        """
        Rule 10: Prevents Character A from quoting Character B's distinctive phrase
        if Character A was not physically present in the room when it was spoken.
        """
        if node.node_type != ASTNodeType.DIALOGUE or not node.speaker:
            return None

        # Distinctive coined phrases mapped to their coining speaker
        tracked_phrases = coined_phrases or {
            "jello shots": "HAYLEY",
            "petroleum in your ass": "HAYLEY",
            "full kardashian": "HAYLEY",
            "dismantle the capitalist": "HAYLEY",
        }

        speaker_norm = EpistemicMatrix.normalize_character_id(node.speaker)
        text_lower = node.content.lower()

        for phrase, coining_char in tracked_phrases.items():
            coining_norm = EpistemicMatrix.normalize_character_id(coining_char)
            if coining_norm != speaker_norm and phrase in text_lower:
                if not spatial.was_present_when_spoken(speaker_norm, phrase):
                    return LintViolation(
                        rule_id="RULE_10_TELEPATHIC_PHRASE_LEAK",
                        line_number=node.line_number,
                        speaker=node.speaker,
                        offending_text=node.content,
                        diagnostic_message=f"Character '{node.speaker}' telepathically quoted '{phrase}', which was coined by '{coining_char}' while '{node.speaker}' was absent from the room.",
                        repair_instruction=f"Remove the telepathic quote. '{node.speaker}' cannot know this phrase unless informed by another character on screen.",
                        severity="ERROR",
                    )
        return None

    @staticmethod
    def check_exposition_budget(
        node: ASTElement,
        max_exposition_words: int = 45,
    ) -> Optional[LintViolation]:
        """
        Rule 11: Soft warning for long, uninterrupted exposition/deposition monologues.
        Exposition is legitimate in comedy, so this produces a WARNING with an allowable budget.
        """
        if node.node_type != ASTNodeType.DIALOGUE:
            return None

        text = node.content.strip()
        words = text.split()

        # Check for exposition buzzwords indicating legalistic plot recaps or AI notebook reading
        exposition_markers = [
            "let me explain",
            "as you know",
            "according to the records",
            "my entire backstory",
            "in the previous episode",
            "what happened was that",
            "for context",
            "undercover notes",
            "read your notes",
            "page one:",
        ]

        text_lower = text.lower()
        has_marker = any(m in text_lower for m in exposition_markers)

        if has_marker and len(words) > max_exposition_words:
            return LintViolation(
                rule_id="RULE_11_EXPOSITION_BUDGET_WARNING",
                line_number=node.line_number,
                speaker=node.speaker,
                offending_text=text[:80] + "...",
                diagnostic_message=f"Dialogue block contains {len(words)} words of uninterrupted backstory recap, exceeding the {max_exposition_words}-word budget.",
                repair_instruction="Break up the exposition into shorter exchanges with character interruptions or physical comedy blocking.",
                severity="WARNING",
            )
        return None

    @staticmethod
    def check_director_shorthand(
        node: ASTElement,
    ) -> Optional[LintViolation]:
        """
        Rule 12: Bans writer/director shorthand inside parentheticals (e.g. '(full Kardashian cadence)').
        """
        if node.node_type != ASTNodeType.PARENTHETICAL:
            return None

        text_lower = node.content.lower()
        forbidden_shorthand = [
            r"\bcadence\b",
            r"\bstyle of\b",
            r"\bhomage\b",
            r"\breferencing\b",
            r"\bkardashian\b",
            r"\bboondocks\b",
            r"\bscoomp\b",
        ]

        for pat in forbidden_shorthand:
            if re.search(pat, text_lower):
                return LintViolation(
                    rule_id="RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL",
                    line_number=node.line_number,
                    speaker=node.speaker,
                    offending_text=node.content,
                    diagnostic_message=f"Parenthetical '{node.content}' uses meta director shorthand instead of acting delivery instructions.",
                    repair_instruction="Replace writer shorthand with an in-universe physical action or emotional attitude (e.g. '(deadpan)', '(vocal fry, unbothered)').",
                    severity="ERROR",
                )
        return None

    @staticmethod
    def check_cognitive_saturation_amnesia(
        node: ASTElement,
        epistemic: EpistemicMatrix,
        prior_committed_script: str = "",
    ) -> Optional[LintViolation]:
        """
        Rule 13: Enforces Theory of Mind invariants for characters in COGNITIVE_SUPPRESSION or AMNESIA_BLANK.
        1. Proactive Recall Violation: If a fact is suppressed, character cannot proactively talk about it.
        2. Lucid Recall Violation: If prompted by another character about a suppressed fact (e.g. 'What about Jeff?'),
           the character must exhibit genuine amnesic confusion ('What is a Jeff?!') rather than lucid, composed recall.
        """
        if node.node_type != ASTNodeType.DIALOGUE or not node.speaker:
            return None

        speaker_norm = EpistemicMatrix.normalize_character_id(node.speaker)
        text_lower = node.content.lower()

        # Check all facts for suppression/amnesia on this speaker
        for fact_id, fact in epistemic.facts.items():
            belief = epistemic.get_belief(speaker_norm, fact_id)
            if belief not in (EpistemicBelief.COGNITIVE_SUPPRESSION, EpistemicBelief.AMNESIA_BLANK):
                continue

            # Check if any embargo tokens of the suppressed fact appear in this dialogue
            matched_token = None
            for token in fact.embargo_tokens:
                pattern = rf"\b{re.escape(token.lower())}\b"
                if re.search(pattern, text_lower):
                    matched_token = token
                    break

            if not matched_token:
                continue

            # Token appeared: Was this fact just prompted by another character in immediate prior lines?
            prior_lower = prior_committed_script[-400:].lower() if prior_committed_script else ""
            was_prompted = any(tok.lower() in prior_lower for tok in fact.embargo_tokens)

            if not was_prompted:
                # Proactive recall while cognitively suppressed is a hard violation
                return LintViolation(
                    rule_id="RULE_13_COGNITIVE_SATURATION_LEAK",
                    line_number=node.line_number,
                    speaker=node.speaker,
                    offending_text=node.content,
                    diagnostic_message=f"Character '{speaker_norm}' proactively recalled '{matched_token}', but fact '{fact_id}' is in {belief.name} due to transformation/sensory overload.",
                    repair_instruction=f"Remove proactive reference to '{matched_token}'. Character has zero bandwidth to recall this domestic fact.",
                    severity="ERROR",
                )
            else:
                # Character was prompted: check if they responded with amnesic confusion vs lucid recall
                confusion_markers = [
                    "what is a", "who?", "what?", "who is", "je...", "what's a",
                    "don't know", "never heard", "blank", "barely form words"
                ]
                has_confusion = any(cm in text_lower for cm in confusion_markers)

                # Explicit lucid affirmation markers that break amnesia
                lucid_affirmation_markers = [
                    "i love my husband",
                    "i must stay faithful",
                    "my marriage vows",
                    "i remember him clearly",
                    "let me call my husband",
                ]
                is_lucid_affirmation = any(lam in text_lower for lam in lucid_affirmation_markers)

                if is_lucid_affirmation or not has_confusion:
                    return LintViolation(
                        rule_id="RULE_13_COGNITIVE_SATURATION_LEAK",
                        line_number=node.line_number,
                        speaker=node.speaker,
                        offending_text=node.content,
                        diagnostic_message=f"Character '{speaker_norm}' was prompted about '{fact_id}', but gave a lucid response instead of exhibiting amnesic disorientation.",
                        repair_instruction=f"Reflect amnesic blankness (e.g. 'Je...ff? What? Who? What is a Jeff?!') to honor sensory overload.",
                        severity="ERROR",
                    )

        return None
