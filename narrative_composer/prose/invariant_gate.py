"""
Invariant Verification Gate for the Noir Module 1 Prose Engine.
Enforces upstream drama invariants before any proposed rewrite can become a candidate proposal:
1. Protected canonical dialogue and required tokens must remain intact.
2. Prop FSM state consistency (e.g. cannot illuminate or interact with a destroyed prop).
3. Epistemic boundaries (no unearned secret reveals or telepathic knowledge).
4. Meta-commentary stripping (strips conversational preamble like 'Here is your prose:').
"""

import re
import uuid
from typing import List, Tuple
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.prose.models import (
    ProseDiagnosticReport,
    ProseRewriteProposal,
    ProseRewriteRequest,
)
from narrative_composer.prose.protected_spans import ProtectedSpanProtector


class InvariantGate:
    """Referee that audits candidate prose text against dramatic and physical invariants."""

    @staticmethod
    def clean_candidate_text(raw_text: str) -> str:
        """Strips markdown code fences and conversational preamble if the model emitted them."""
        text = raw_text.strip()
        # Strip outer markdown block ```markdown ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:markdown|text)?\s*([\s\S]*?)\s*```", text)
        if fence_match:
            text = fence_match.group(1).strip()

        # Strip conversational AI prefixes
        prefixes = [
            r"^(?:here(?:'s| is) (?:the|your) (?:rewritten|improved|conditioned) prose:?\s*)",
            r"^(?:sure,? here(?:'s| is) (?:the|a) rewrite:?\s*)",
            r"^(?:rewritten prose:?\s*)",
        ]
        for p in prefixes:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

        return text

    @classmethod
    def verify_prop_states(
        cls, candidate_text: str, active_props: dict[str, str]
    ) -> List[str]:
        """
        Ensures the candidate text does not violate physical states of props.
        For example: cannot turn on, illuminate, or drink from an empty/broken prop.
        """
        violations = []
        lowered = candidate_text.lower()

        for prop_name, state in active_props.items():
            state_lower = state.lower()
            tokens = [w for w in prop_name.lower().split("_") if len(w) > 2]
            if not tokens:
                tokens = [prop_name.lower()]

            # Match either the primary keyword or tokens with intervening words (e.g. 'Gloria the flamingo lamp')
            joined_pattern = r"\b" + r"\b.*?\b".join(re.escape(t) for t in tokens) + r"\b"
            primary_token = re.escape(tokens[0])

            if state_lower in ("broken", "destroyed", "shattered"):
                # Check for impossible active usage verbs
                patterns = [
                    rf"\b(?:turns\s+on|switches\s+on|lights|illuminates|plugs\s+in)\s+.*?(?:{joined_pattern}|\b{primary_token}\b)",
                    rf"\b(?:{joined_pattern}|\b{primary_token}\b)\s+(?:glows|shines|lights\s+up|stands\s+sturdy)\b",
                ]
                for pat in patterns:
                    if re.search(pat, lowered):
                        violations.append(
                            f"Physical impossibility: Prop '{prop_name}' is {state}, "
                            f"but proposed prose attempts to activate or illuminate it."
                        )

            elif state_lower == "empty":
                # Check for drinking/consuming from empty prop
                if re.search(rf"\b(?:drinks|sips|gulps)\s+(?:from\s+)?.*?(?:{joined_pattern}|\b{primary_token}\b)", lowered):
                    violations.append(
                        f"Physical impossibility: Prop '{prop_name}' is empty, "
                        f"but proposed prose depicts drinking from it."
                    )

        return violations

    @classmethod
    def verify_epistemic_bounds(
        cls, candidate_text: str, character_epistemic_scope: dict[str, List[str]]
    ) -> List[str]:
        """
        Ensures characters do not speak or act upon unlearned secrets or facts.
        """
        violations = []
        lowered = candidate_text.lower()

        for char, secrets in character_epistemic_scope.items():
            for secret in secrets:
                # If secret is an unknown secret marked with 'unknown_' or 'secret_'
                if secret.startswith("unknown_") or "unrevealed" in secret:
                    secret_token = secret.replace("unknown_", "").replace("unrevealed_", "").replace("_", " ")
                    if secret_token in lowered:
                        violations.append(
                            f"Epistemic leak: Character '{char}' is not yet aware of '{secret_token}', "
                            f"but it was referenced or revealed in dialogue/action."
                        )

        return violations

    @classmethod
    def audit_rewrite(
        cls, candidate_text: str, request: ProseRewriteRequest
    ) -> Tuple[bool, List[str], str]:
        """
        Runs complete invariant audit.
        Returns (is_valid, list_of_violations, cleaned_text).
        """
        cleaned_text = cls.clean_candidate_text(candidate_text)
        violations: List[str] = []

        if not cleaned_text:
            return False, ["Candidate text is empty."], ""

        # 1. Protected Spans & Canonical Words
        is_spans_valid, span_errors = ProtectedSpanProtector.verify_all(
            cleaned_text, request.protected_spans
        )
        if not is_spans_valid:
            violations.extend(span_errors)

        # 2. Prop FSM State Integrity
        prop_errors = cls.verify_prop_states(cleaned_text, request.active_props)
        violations.extend(prop_errors)

        # 3. Epistemic Knowledge Boundaries
        epistemic_errors = cls.verify_epistemic_bounds(cleaned_text, request.character_epistemic_scope)
        violations.extend(epistemic_errors)

        return len(violations) == 0, violations, cleaned_text

    @classmethod
    def create_verified_proposal(
        cls,
        candidate_text: str,
        request: ProseRewriteRequest,
        diagnostics_before: ProseDiagnosticReport,
        model_provider: str = "mock",
        model_name: str = "synthetic-v1",
    ) -> Tuple[ProseRewriteProposal, List[str]]:
        """
        Validates candidate rewrite, runs post-rewrite diagnostics, and returns typed ProseRewriteProposal.
        """
        from narrative_composer.prose.validation import validate_rewrite
        is_valid, violations, cleaned_text = validate_rewrite(candidate_text, request)

        # Post-rewrite diagnostics
        diagnostics_after = ProseDiagnosticsAnalyzer.analyze(
            cleaned_text,
            span_id=request.target_span_id,
            target_psychic_distance=request.target_psychic_distance,
        )

        proposal = ProseRewriteProposal(
            proposal_id=f"prop_{uuid.uuid4().hex[:12]}",
            request_id=request.request_id,
            project_id=request.project_id,
            document_id=request.document_id,
            base_revision=request.base_revision,
            target_span_id=request.target_span_id,
            proposed_text=cleaned_text,
            original_text=request.original_text,
            diagnostics_before=diagnostics_before,
            diagnostics_after=diagnostics_after,
            protected_words_verified=ProtectedSpanProtector.verify_all(cleaned_text, request.protected_spans)[0],
            epistemic_verified=not cls.verify_epistemic_bounds(cleaned_text, request.character_epistemic_scope),
            validation_errors=violations,
            model_provider=model_provider,
            model_name=model_name,
        )

        return proposal, violations
