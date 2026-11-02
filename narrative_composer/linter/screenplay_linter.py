"""
Screenplay Linter Orchestrator.
Coordinates running all invariant rules on AST nodes and generating repair reports.
"""

from __future__ import annotations
from typing import List, Set, Optional
from ..models.ast_nodes import ASTElement
from ..models.epistemic import EpistemicMatrix
from ..models.spatial_fsm import SpatialGraph
from .rules import LinterRuleEngine, LintViolation


class ScreenplayLinter:
    def __init__(self, epistemic: EpistemicMatrix, spatial: SpatialGraph):
        self.epistemic = epistemic
        self.spatial = spatial

    def lint_beat(
        self,
        ast: List[ASTElement],
        active_room_id: str,
        prior_committed_script: str = "",
        discovered_features: Optional[Set[str]] = None
    ) -> List[LintViolation]:
        """
        Runs the full suite of 6 invariant checks across all AST elements in a beat.
        Returns a list of LintViolation objects (empty if PASS).
        """
        if discovered_features is None:
            discovered_features = set()

        violations: List[LintViolation] = []

        for node in ast:
            # Rule 1: Token Embargo
            v1 = LinterRuleEngine.check_token_embargo(node, self.epistemic)
            if v1:
                violations.append(v1)

            # Rule 2: Zombie / Depleted Props
            v2 = LinterRuleEngine.check_zombie_prop(node, self.spatial)
            if v2:
                violations.append(v2)

            # Rule 3: Phantom Citations
            v3 = LinterRuleEngine.check_phantom_citation(node, prior_committed_script)
            if v3:
                violations.append(v3)

            # Rule 4: Double Discovery
            v4 = LinterRuleEngine.check_double_discovery(node, discovered_features)
            if v4:
                violations.append(v4)

            # Rule 5: Speaker Room Presence
            v5 = LinterRuleEngine.check_speaker_room_presence(node, active_room_id, self.spatial)
            if v5:
                violations.append(v5)

            # Rule 6: Prop Accessibility
            v6 = LinterRuleEngine.check_prop_accessibility(node, self.spatial)
            if v6:
                violations.append(v6)

            # Rule 7: Debris Hazard Safety
            v7 = LinterRuleEngine.check_debris_hazard_safety(node, active_room_id, self.spatial)
            if v7:
                violations.append(v7)

            # Rule 8: Anatomical / Transformation Persona Mismatch
            v8 = LinterRuleEngine.check_transformation_persona_consistency(node, self.spatial)
            if v8:
                violations.append(v8)

            # Rule 9: Source-Name Embargo
            v9 = LinterRuleEngine.check_source_name_embargo(node)
            if v9:
                violations.append(v9)

            # Rule 10: Telepathic Phrase Leak
            v10 = LinterRuleEngine.check_telepathic_phrase_leak(node, self.spatial)
            if v10:
                violations.append(v10)

            # Rule 11: Exposition Budget Warning
            v11 = LinterRuleEngine.check_exposition_budget(node)
            if v11:
                violations.append(v11)

            # Rule 12: Director Shorthand Parenthetical
            v12 = LinterRuleEngine.check_director_shorthand(node)
            if v12:
                violations.append(v12)

            # Rule 13: Cognitive Saturation & Amnesia Invariant
            v13 = LinterRuleEngine.check_cognitive_saturation_amnesia(node, self.epistemic, prior_committed_script)
            if v13:
                violations.append(v13)

        return violations

    def lint_full_script(self, ast: List[ASTElement]) -> List[LintViolation]:
        """
        Lints a complete multi-scene script sequentially, dynamically tracking
        room transitions, character entries, and fact discoveries.
        """
        from ..models.ast_nodes import ASTNodeType
        from ..models.spatial_fsm import ItemLifecycle
        from ..models.epistemic import EpistemicBelief

        violations: List[LintViolation] = []
        active_room = "living_room"
        active_speaker = None
        discovered_features: Set[str] = set()
        prior_text_buffer: List[str] = []

        for node in ast:
            content_lower = node.content.lower()

            # Track active speaker cue
            if node.node_type == ASTNodeType.CHARACTER:
                active_speaker = node.content.upper().strip()

            # 1. Dynamic Room Tracking via Scene Headings (Milestone 1: SluglineParser)
            if node.node_type == ASTNodeType.SCENE_HEADING:
                from ..parser.slugline_parser import SluglineParser
                parsed_slug = SluglineParser.parse(node.content)
                active_room = parsed_slug.canonical_room_id
                if parsed_slug.aliases:
                    self.spatial.room_aliases[active_room] = parsed_slug.aliases

            # 2. Dynamic Character Movement via Action Lines & Physical Parentheticals
            if node.node_type == ASTNodeType.PARENTHETICAL and active_speaker:
                if any(w in content_lower for w in ["stepping", "enters", "walking", "standing", "behind", "sliding", "approaching"]):
                    self.spatial.move_character(active_speaker, active_room)

            if node.node_type == ASTNodeType.ACTION:
                # Direct movement & presence tracking
                if any(phrase in content_lower for phrase in [
                    "stella heads out", "stella walks into", "stella floats into",
                    "stella sprawls", "stella enters", "stella lies sprawled",
                    "stella stalks downstairs", "stella's velvet couch", "stella bolts",
                    "stella stands", "stella sits", "stella collapses", "stella scrambles",
                    "stella curls", "stella sits wedged", "poking stella", "steve sits"
                ]):
                    self.spatial.move_character("STELLA", active_room)
                elif "stella" in content_lower or "steve" in content_lower:
                    self.spatial.move_character("STELLA", active_room)

                if any(phrase in content_lower for phrase in [
                    "francine enters", "francine walks into", "francine picks",
                    "francine storms", "francine sweeps", "francine rushes",
                    "francine turns", "francine charges", "francine sits", "francine stares",
                    "francine ling"
                ]):
                    self.spatial.move_character("FRANCINE", active_room)
                elif "francine" in content_lower:
                    self.spatial.move_character("FRANCINE", active_room)

                if "hayley" in content_lower and any(phrase in content_lower for phrase in ["heads upstairs", "walks upstairs", "goes upstairs"]):
                    self.spatial.move_character("HAYLEY", "hallway")
                elif any(phrase in content_lower for phrase in [
                    "coming down the stairs", "stands center", "glides",
                    "drifts", "hayley enters", "hayley floats", "hayley tries",
                    "hayley squares", "hayley doubles", "hayley's neon yoga mat",
                    "hayley freezes", "wedges", "hayley sits", "hayley stands", "influencer bbl hayley"
                ]):
                    self.spatial.move_character("HAYLEY", active_room)
                elif "hayley" in content_lower:
                    self.spatial.move_character("HAYLEY", active_room)

                if any(phrase in content_lower for phrase in [
                    "holly graham", "holly lounges", "holly sets down",
                    "holly circles", "holly enters", "holly in her gold", "holly smiles", "holly glides"
                ]):
                    self.spatial.move_character("HOLLY GRAHAM", active_room)
                    self.spatial.move_character("HOLLY", active_room)
                elif "holly" in content_lower:
                    self.spatial.move_character("HOLLY GRAHAM", active_room)
                    self.spatial.move_character("HOLLY", active_room)

                if "roger" in content_lower:
                    self.spatial.move_character("ROGER", active_room)

                if "rainee" in content_lower:
                    self.spatial.move_character("RAINEE", active_room)

            # 3. Check Single AST Element against active state (BEFORE applying node's destructive deltas)
            prior_committed = "\n".join(prior_text_buffer)
            element_violations = self.lint_beat(
                ast=[node],
                active_room_id=active_room,
                prior_committed_script=prior_committed,
                discovered_features=discovered_features
            )
            violations.extend(element_violations)

            # 4. Apply State Mutations resulting from this node's action/dialogue
            if node.node_type == ASTNodeType.ACTION:
                # Track physical prop events & debris hazards in action lines
                if "gloria" in content_lower and "shatters" in content_lower:
                    if "gloria_lamp" in self.spatial.items:
                        self.spatial.items["gloria_lamp"].lifecycle = ItemLifecycle.DESTROYED
                    self.spatial.add_debris("gloria_lamp_shards", "gloria_lamp", "living_room", material="ceramic_shards")

                if any(w in content_lower for w in ["sweeps up", "cleans up the ceramic", "cleans up the shards", "dustpan"]):
                    self.spatial.clear_debris("gloria_lamp_shards", "FRANCINE")

                if "top two collar buttons" in content_lower:
                    if "stella_polo_buttons" in self.spatial.items:
                        self.spatial.items["stella_polo_buttons"].pop_charges(2)
                if "remaining polo buttons rip off" in content_lower:
                    if "stella_polo_buttons" in self.spatial.items:
                        self.spatial.items["stella_polo_buttons"].pop_charges(4)
                if "rocket ships" in content_lower:
                    self.epistemic.set_belief("FRANCINE", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("STELLA", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("HAYLEY", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    discovered_features.add("rocket_ships")

                # Track anatomical transformations
                from ..models.spatial_fsm import AnatomicalStage
                if any(w in content_lower for w in ["vanderbooben marrow", "autoinjector", "marrow harvest"]):
                    self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_ROGER_DOME)
                    self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])
                elif any(w in content_lower for w in ["calabasas stabilizer", "kardashian stabilizer", "influencer bbl hayley", "make it clap"]):
                    self.spatial.set_character_stage("HAYLEY", AnatomicalStage.HAYLEY_BBL_INFLUENCER)
                    self.epistemic.suppress_facts_for_character("HAYLEY", fact_ids=["fact_husband_jeff"])

                if "nerd saturation: 20%" in content_lower or ("cardio-cube" in content_lower and "20%" in content_lower):
                    self.spatial.set_character_stage("STELLA", AnatomicalStage.STELLA_NERD_20)
                elif "nerd saturation: 80%" in content_lower or "saturation reaches 80%" in content_lower:
                    self.spatial.set_character_stage("STELLA", AnatomicalStage.STELLA_NERD_80)
                elif any(w in content_lower for w in ["nerd saturation: 150%", "steve smith in a strapless bra", "big tiddy steve"]):
                    self.spatial.set_character_stage("STELLA", AnatomicalStage.STELLA_BIG_TIDDY_STEVE)

            # Dynamic Knowledge Progression & Witness Log resulting from delivered dialogue
            if node.node_type == ASTNodeType.DIALOGUE and node.speaker:
                self.spatial.record_utterance(node.line_number, node.speaker, active_room, node.content)
                # When Francine delivers the Steve monologue:
                if "named him steve" in content_lower or "call you steve" in content_lower:
                    self.epistemic.set_belief("FRANCINE", "fact_steve_identity", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("STELLA", "fact_steve_identity", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("HAYLEY", "fact_steve_identity", EpistemicBelief.KNOWN_TRUE)

                # When Francine discovers the rocket ships:
                if "little rocket ships" in content_lower:
                    self.epistemic.set_belief("FRANCINE", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("STELLA", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    self.epistemic.set_belief("HAYLEY", "fact_rocket_ships", EpistemicBelief.KNOWN_TRUE)
                    discovered_features.add("rocket_ships")

                # When Hayley experiences the amnesic blank:
                if "what is a jeff" in content_lower or "what's a jeff" in content_lower:
                    self.epistemic.trigger_amnesic_blank("HAYLEY", "fact_husband_jeff")

            # Append to buffer
            prior_text_buffer.append(node.content)

        return violations

    @staticmethod
    def format_diagnostic_report(violations: List[LintViolation]) -> str:
        """
        Formats violations into an actionable prompt block for the LLM auto-repair pass.
        """
        if not violations:
            return "NO CONTINUITY VIOLATIONS DETECTED (PASS)."

        lines = [
            f"=== CRITICAL CONTINUITY VIOLATIONS DETECTED ({len(violations)} ERRORS) ===",
            "Your draft contains narrative logic errors that must be resolved before proceeding:",
            ""
        ]
        for idx, v in enumerate(violations, start=1):
            lines.append(f"[{idx}] {v.rule_id} at line {v.line_number}:")
            lines.append(f"    OFFENDING TEXT: \"{v.offending_text}\"")
            lines.append(f"    DIAGNOSTIC: {v.diagnostic_message}")
            lines.append(f"    INSTRUCTION: {v.repair_instruction}")
            lines.append("")

        lines.append("Please rewrite the beat text to resolve every violation listed above while preserving comedic timing.")
        return "\n".join(lines)
