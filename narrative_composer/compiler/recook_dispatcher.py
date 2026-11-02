"""
Dual-Tier Recook Proposal Dispatcher.
Part of Milestone 4: Automated Recook Loop.

Classifies screenplay linter violations into:
- Tier 1: Deterministic candidate replacement for a specific source line.
- Tier 2: Model-generated candidate for a specific source line.
All candidates require author review; dispatch does not rewrite the manuscript.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re
import hashlib
import uuid
from typing import Dict, List, Optional, Tuple, Any

from ..models.ast_nodes import ASTElement, ASTNodeType
from ..linter.rules import LintViolation
from ..models.spatial_fsm import SpatialGraph, AnatomicalStage
from ..models.epistemic import EpistemicMatrix, EpistemicBelief
from ..prose.ledger import RevisionLedger
from ..prose.models import (
    DecisionRecord,
    DecisionType,
    ProseRewriteProposal,
    ProseRewriteRequest,
    ProtectedSpan,
    SpanCategory,
)
from ..prose.style_engine import StyleProfileRepository, STANDARD_DRAMATIC
from ..prose.providers import create_prose_provider
from ..prose.invariant_gate import InvariantGate
from ..prose.diagnostics import ProseDiagnosticsAnalyzer
from ..prose.prompt_assembler import PromptAssembler
from ..prose.validation import validate_rewrite


class DispatchTier(str, Enum):
    TIER_1_SURGICAL = "tier_1_surgical"
    TIER_2_PROSE_REWRITE = "tier_2_prose_rewrite"
    INFORMATIONAL = "informational"


@dataclass
class PatchRecord:
    rule_id: str
    tier: DispatchTier
    original_text: str
    patched_text: str
    line_number: int
    description: str


@dataclass
class RecookReport:
    total_violations_evaluated: int
    tier1_patches_applied: int
    tier2_rewrites_applied: int
    patch_records: List[PatchRecord] = field(default_factory=list)
    reconstructed_script: str = ""
    is_fully_resolved: bool = False
    pending_proposals: List[Dict[str, Any]] = field(default_factory=list)


class DispatchRuleClassifier:
    """Classifies linter violations into Tier 1 (surgical) vs Tier 2 (LLM recook)."""

    TIER_1_RULES = {
        "RULE_9_SOURCE_NAME_EMBARGO",
        "RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL",
        "RULE_1_FORBIDDEN_TOKEN_EMBARGO",
        "RULE_7_DEBRIS_HAZARD_SAFETY",
        "RULE_13_COGNITIVE_SATURATION_LEAK",
    }

    TIER_2_RULES = {
        "RULE_8_ANATOMICAL_PERSONA_MISMATCH",
        "RULE_11_EXPOSITION_BUDGET_WARNING",
        "RULE_10_TELEPATHIC_PHRASE_LEAK",
    }

    @classmethod
    def classify(cls, violation: LintViolation) -> DispatchTier:
        if violation.rule_id in cls.TIER_1_RULES:
            return DispatchTier.TIER_1_SURGICAL
        elif violation.rule_id in cls.TIER_2_RULES:
            return DispatchTier.TIER_2_PROSE_REWRITE
        return DispatchTier.INFORMATIONAL


class SurgicalPatcher:
    """Applies deterministic, mathematically predictable text replacements to resolve Tier 1 errors."""

    TRADEMARK_REPLACEMENTS = [
        (re.compile(r"\bKardashian stabilizer\b", re.IGNORECASE), "Calabasas stabilizer"),
        (re.compile(r"\bKardashian blend\b", re.IGNORECASE), "Reality Queen blend"),
        (re.compile(r"\bKardashians\b", re.IGNORECASE), "Reality Queens"),
        (re.compile(r"\bKardashian\b", re.IGNORECASE), "Reality Queen"),
        (re.compile(r"\bBoondocks\b", re.IGNORECASE), "urban animation satire"),
        (re.compile(r"\bHot Scoomp\b", re.IGNORECASE), "Hot Scoop"),
        (re.compile(r"\bflat-to-fat\b", re.IGNORECASE), "rapid expansion"),
        (re.compile(r"\baugmentation addiction\b", re.IGNORECASE), "aesthetic obsession"),
    ]

    PARENTHETICAL_REPLACEMENTS = [
        (re.compile(r"\(whining in Roger's high-pitched cadence\)", re.IGNORECASE), "(shrill, petulant whine)"),
        (re.compile(r"\(.*?\bstyle of\b.*?\)", re.IGNORECASE), "(deadpan)"),
        (re.compile(r"\(.*?\bkardashian\b.*?\)", re.IGNORECASE), "(vocal fry, unbothered)"),
        (re.compile(r"\(.*?\breferencing\b.*?\)", re.IGNORECASE), "(wryly)"),
        (re.compile(r"\(.*?\bhomage\b.*?\)", re.IGNORECASE), "(sarcastic)"),
    ]

    @classmethod
    def patch_violation(cls, violation: LintViolation, script_text: str) -> Tuple[str, Optional[PatchRecord]]:
        """Patches a single Tier 1 violation in the script text."""
        rule_id = violation.rule_id
        original = violation.offending_text
        patched = original

        if rule_id == "RULE_9_SOURCE_NAME_EMBARGO":
            for pat, repl in cls.TRADEMARK_REPLACEMENTS:
                if pat.search(patched):
                    patched = pat.sub(repl, patched)
        elif rule_id == "RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL":
            for pat, repl in cls.PARENTHETICAL_REPLACEMENTS:
                if pat.search(patched):
                    patched = pat.sub(repl, patched)
        elif rule_id == "RULE_1_FORBIDDEN_TOKEN_EMBARGO":
            patched = re.sub(r"\b(?:five hundred dollars|\$500)\b", "five bills", patched, flags=re.IGNORECASE)
        elif rule_id == "RULE_7_DEBRIS_HAZARD_SAFETY":
            patched = re.sub(
                r"\b(walks|steps|strides)\s+barefoot\b",
                r"\1 barefoot, tiptoeing carefully over the ceramic shards",
                patched,
                flags=re.IGNORECASE
            )
        elif rule_id == "RULE_13_COGNITIVE_SATURATION_LEAK":
            # Do not invent memory loss or replace an author's dialogue with it.
            return script_text, None

        if patched != original and original in script_text:
            new_script = script_text.replace(original, patched, 1)
            rec = PatchRecord(
                rule_id=rule_id,
                tier=DispatchTier.TIER_1_SURGICAL,
                original_text=original,
                patched_text=patched,
                line_number=violation.line_number,
                description=f"Proposed {rule_id} replacement"
            )
            return new_script, rec

        return script_text, None


class ProseRecooker:
    """Executes closed-loop neural conditioning on complex Tier 2 prose or dialogue violations."""

    def __init__(self, provider_type: str = "mock", provider=None):
        self.provider = provider if provider is not None else create_prose_provider(provider_type)
        self.repo = StyleProfileRepository()
        self.profile = self.repo.get_style_profile("standard_dramatic") or STANDARD_DRAMATIC

    def recook_span(
        self,
        span_text: str,
        violation: LintViolation,
        active_props: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, bool]:
        """Runs prose conditioning on a target span with the standard profile and invariants."""
        span_id = f"L{violation.line_number}"
        diagnostics = ProseDiagnosticsAnalyzer.analyze(span_text, span_id=span_id)

        req = ProseRewriteRequest(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            project_id="hot_scoomp",
            document_id="master_screenplay",
            base_revision=1,
            target_span_id=span_id,
            original_text=span_text,
            category=SpanCategory.DIALOGUE,
            # The offending span is precisely what must change, so it is not protected.
            protected_spans=[],
            active_props=active_props or {},
            style_profile_id=self.profile.profile_id,
        )

        prompt = PromptAssembler.assemble(
            request=req,
            diagnostics=diagnostics,
            style_profile=self.profile,
            approved_edits=[],
            reference_passages=[],
        )

        raw_text = self.provider.generate_rewrite(req, prompt)
        clean_text = InvariantGate.clean_candidate_text(raw_text)
        ok, _, clean_text = validate_rewrite(clean_text, req)
        return clean_text, ok


class RecookDispatcher:
    """
    Main orchestrator that evaluates violations, dispatches surgical patches
    and neural recooks, and logs the complete audit trail into the RevisionLedger.
    """

    def __init__(self, ledger: Optional[RevisionLedger] = None, provider_type: str = "mock"):
        self.ledger = ledger or RevisionLedger()
        self.surgical_patcher = SurgicalPatcher()
        self.prose_recooker = ProseRecooker(provider_type=provider_type)

    def dispatch_all(
        self,
        script_text: str,
        violations: List[LintViolation],
        active_props: Optional[Dict[str, str]] = None,
        command_id: Optional[str] = None
    ) -> RecookReport:
        """
        Plans dual-tier candidates without changing the supplied manuscript.
        """
        current_text = script_text
        base_hash = hashlib.sha256(script_text.encode('utf-8')).hexdigest()
        report = RecookReport(
            total_violations_evaluated=len(violations),
            tier1_patches_applied=0,
            tier2_rewrites_applied=0,
        )

        for v in violations:
            tier = DispatchRuleClassifier.classify(v)

            if tier == DispatchTier.TIER_1_SURGICAL:
                lines = script_text.splitlines(keepends=True)
                index = v.line_number - 1
                if not (0 <= index < len(lines)):
                    continue
                _, patch_rec = self.surgical_patcher.patch_violation(v, lines[index])
                if patch_rec:
                    report.patch_records.append(patch_rec)
                    base_rev = self.ledger.get_current_revision("hot_scoomp", "master_screenplay")
                    proposal = ProseRewriteProposal(
                        proposal_id=f"prop_{v.rule_id}_{uuid.uuid4().hex[:6]}",
                        request_id=f"req_{v.rule_id}",
                        target_span_id=f"L{v.line_number}",
                        document_id="master_screenplay",
                        project_id="hot_scoomp",
                        base_revision=base_rev,
                        proposed_text=patch_rec.patched_text,
                        original_text=patch_rec.original_text,
                        model_provider="surgical_patcher",
                    )
                    self.ledger.record_proposal(proposal)
                    report.pending_proposals.append({'proposal_id':proposal.proposal_id,
                        'line':v.line_number, 'original':patch_rec.original_text,
                        'proposed':patch_rec.patched_text, 'rule_id':v.rule_id,
                        'base_hash':base_hash, 'decision':'pending author review'})

            elif tier == DispatchTier.TIER_2_PROSE_REWRITE:
                # Earlier tier-1 patches may have rewritten this line already, so the
                # violation's recorded offending_text can be stale. Resolve the span
                # against the current text by line number instead.
                lines = current_text.splitlines(keepends=True)
                idx = v.line_number - 1
                if not (0 <= idx < len(lines)):
                    continue
                line = lines[idx]
                eol = ""
                body = line
                for cand in ("\r\n", "\n"):
                    if body.endswith(cand):
                        eol = cand
                        body = body[: -len(cand)]
                        break

                span_text = v.offending_text if v.offending_text and v.offending_text in body else body
                if not span_text.strip():
                    continue

                recooked_text, ok = self.prose_recooker.recook_span(
                    span_text, v, active_props=active_props
                )
                if not ok or not recooked_text.strip():
                    continue

                report.pending_proposals.append({'line': v.line_number, 'original': span_text,
                    'proposed': recooked_text, 'rule_id': v.rule_id, 'base_hash':base_hash,
                    'decision': 'pending author review'})
                # Batch mode cannot manufacture the author's semantic approval.
                continue

        report.reconstructed_script = current_text
        report.is_fully_resolved = not violations  # Only a fresh checker can establish resolution after edits.
        return report
