"""
Selective re-cook: propose fixes for individual blocks, then apply only what is accepted.

This plans patches per *block*: every violation is mapped to the block on its line, the tier-1
surgical rewrite or tier-2 neural recook runs against that block's text alone, and the
result is offered for review. Nothing is written until `apply_patch()` is called.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from narrative_composer.compiler.document import Block, BlockRole, Document, parse_document, replace_block_text
from narrative_composer.compiler.recook_dispatcher import (
    DispatchRuleClassifier,
    DispatchTier,
    ProseRecooker,
    SurgicalPatcher,
)
from narrative_composer.linter.rules import LintViolation
from narrative_composer.linter.screenplay_linter import ScreenplayLinter
from narrative_composer.models.epistemic import EpistemicBelief, EpistemicMatrix, NarrativeFact
from narrative_composer.models.spatial_fsm import PhysicalEntity, SpatialGraph
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.prose.providers import ProviderError

# Which block kind a rule is expected to touch, most-specific first.
_ROLE_PREFERENCE: Dict[str, Tuple[BlockRole, ...]] = {
    "RULE_12_DIRECTOR_SHORTHAND_PARENTHETICAL": (BlockRole.PARENTHETICAL,),
    "RULE_7_DEBRIS_HAZARD_SAFETY": (BlockRole.ACTION,),
    "RULE_1_FORBIDDEN_TOKEN_EMBARGO": (BlockRole.DIALOGUE,),
}
_DEFAULT_PREFERENCE = (BlockRole.DIALOGUE, BlockRole.PARENTHETICAL, BlockRole.ACTION)


@dataclass(frozen=True)
class Patch:
    """A single proposed block rewrite. Nothing is mutated until it is applied."""

    block_id: str
    line: int
    rule_id: str
    severity: str
    tier: str
    original: str
    proposed: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "line": self.line,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "tier": self.tier,
            "original": self.original,
            "proposed": self.proposed,
            "rationale": self.rationale,
        }


def _load_manifest(manifest_path: Path) -> Tuple[EpistemicMatrix, SpatialGraph]:
    """Loads the epistemic/spatial manifest without the CLI's exit-on-error behaviour."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    facts = {k: NarrativeFact(**v) for k, v in data.get("facts", {}).items()}
    epistemic = EpistemicMatrix(facts=facts)
    for character, beliefs in data.get("initial_beliefs", {}).items():
        for fact_id, value in beliefs.items():
            epistemic.set_belief(character, fact_id, EpistemicBelief(value))

    props = {k: PhysicalEntity(**v) for k, v in data.get("props", {}).items()}
    spatial = SpatialGraph(
        items=props,
        character_locations=data.get("character_locations", {}),
        room_topology=data.get("room_topology", {}),
    )
    return epistemic, spatial


def _pick_block(document: Document, violation: LintViolation) -> Optional[Block]:
    """Finds the block a violation refers to, preferring the role that rule targets."""
    candidates = [b for b in document.blocks if b.line == violation.line_number]
    if not candidates:
        return None

    preference = _ROLE_PREFERENCE.get(violation.rule_id, _DEFAULT_PREFERENCE)
    for role in preference:
        for block in candidates:
            if block.role == role:
                return block
    return candidates[0]


def _tier1_text(block_text: str, violation: LintViolation) -> Optional[str]:
    """Applies the deterministic surgical rewrite to a single block."""
    new_text, record = SurgicalPatcher.patch_violation(violation, block_text)
    return new_text if record is not None else None


def plan_patches(
    text: str,
    manifest_path: Path,
    provider_type: str = "mock",
    manifest: Optional[dict] = None,
    document: Optional[Document] = None,
    neural_limit: Optional[int] = None,
    stats: Optional[Dict[str, Any]] = None,
    provider: Optional[Any] = None,
) -> List[Patch]:
    """
    Plans per-block fixes for every automatically repairable violation.

    Returns at most one patch per block: several violations on the same block would
    otherwise produce conflicting rewrites computed from the same original text.
    """
    if stats is not None:
        stats.update(neural_attempts=0, neural_skipped=0, provider_errors=[])
    if manifest is None:
        epistemic, spatial = _load_manifest(manifest_path)
    else:
        from narrative_composer.store import _manifest_models
        epistemic, spatial = _manifest_models(manifest)
    violations = ScreenplayLinter(epistemic, spatial).lint_full_script(FountainParser.parse(text))
    if not violations:
        return []

    document = document or parse_document(text)
    recooker = ProseRecooker(provider_type=provider_type, provider=provider) if any(
        DispatchRuleClassifier.classify(v) == DispatchTier.TIER_2_PROSE_REWRITE for v in violations
    ) else None

    patches: List[Patch] = []
    claimed: set[str] = set()
    neural_attempts = 0

    for violation in violations:
        tier = DispatchRuleClassifier.classify(violation)
        if tier == DispatchTier.INFORMATIONAL:
            continue

        block = _pick_block(document, violation)
        if block is None or block.id in claimed:
            continue

        if tier == DispatchTier.TIER_1_SURGICAL:
            proposed = _tier1_text(block.text, violation)
            rationale = f"Surgical {violation.rule_id} patch"
        else:
            if recooker is None:
                continue
            if neural_limit is not None and neural_attempts >= neural_limit:
                if stats is not None:
                    stats['neural_skipped'] += 1
                continue
            neural_attempts += 1
            if stats is not None:
                stats['neural_attempts'] = neural_attempts
            try:
                proposed, ok = recooker.recook_span(block.text, violation, active_props={k: p.lifecycle.value for k, p in spatial.items.items()})
            except ProviderError as exc:
                if stats is None:
                    raise
                stats['provider_errors'].append(str(exc)[:180])
                continue
            proposed = proposed if ok else None
            rationale = f"Neural recook for {violation.rule_id}"

        if not proposed or proposed.strip() == block.text.strip():
            continue

        claimed.add(block.id)
        patches.append(
            Patch(
                block_id=block.id,
                line=block.line,
                rule_id=violation.rule_id,
                severity=violation.severity,
                tier=tier.value,
                original=block.text,
                proposed=proposed.strip(),
                rationale=rationale,
            )
        )

    return patches


def apply_patch(text: str, patch: Patch) -> str:
    """Applies one reviewed patch, rewriting only that block's source line."""
    return replace_block_text(text, patch.block_id, patch.proposed)


def apply_patches(text: str, patches: List[Patch]) -> str:
    """Applies patches in order. Each patch touches one line, so IDs stay stable."""
    updated = text
    for patch in patches:
        updated = apply_patch(updated, patch)
    return updated
