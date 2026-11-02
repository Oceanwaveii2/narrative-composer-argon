"""
Review-first prose conditioning for a finished story.

Finds action blocks that prose diagnostics flag (sensory deficit, monotonous cadence,
observer filters), asks a model to rewrite only that block, validates the candidate against
the invariant gate and a length guard, and reports proposals. Nothing is written until
`--apply` is passed, and each applied rewrite touches exactly one source line.

    python -m narrative_composer.condition --file out/rainee_realm/story.md \
        --out out/rainee_realm/conditioned --provider venice --apply
"""

from __future__ import annotations

import argparse
import json
import math
import re
import uuid
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from narrative_composer.compiler.document import BlockRole, parse_document, replace_block_text
from narrative_composer.compiler.reader_renderer import render_reader
from narrative_composer.linter.html_feedback_loop import HTMLFeedbackLoopVerifier
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.prose.invariant_gate import InvariantGate
from narrative_composer.prose.models import ProseRewriteRequest, SpanCategory
from narrative_composer.prose.prompt_assembler import PromptAssembler
from narrative_composer.prose.providers import create_prose_provider
from narrative_composer.prose.style_engine import STANDARD_DRAMATIC, StyleProfileRepository
from narrative_composer.story import story_theme
from narrative_composer.prose.validation import (context_fields, validate_rewrite, source_hash,
    MIN_REWRITE_RATIO as MIN_RATIO, MAX_REWRITE_RATIO as MAX_RATIO)

MAX_CONDITIONING_ATTEMPTS = 2


@dataclass
class Proposal:
    block_id: str
    line: int
    warnings: List[str]
    original: str
    proposed: str
    accepted: bool
    reason: str
    base_hash: str = ''
    reviewed: bool = False
    attempt_reasons: List[str] = field(default_factory=list)
    provider: str = ''
    model_name: str = ''
    reasoning_effort: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "line": self.line,
            "warnings": self.warnings,
            "original": self.original,
            "proposed": self.proposed,
            "accepted": self.accepted,
            "reason": self.reason,
            'base_hash': self.base_hash,
            'decision': 'accepted by author' if self.reviewed else 'pending review' if self.accepted else 'rejected',
            'attempt_count': len(self.attempt_reasons),
            'attempt_reasons': list(self.attempt_reasons),
            'provider': self.provider, 'model_name': self.model_name, 'reasoning_effort': self.reasoning_effort,
        }


def plan_conditioning(
    text: str,
    provider: Any,
    profile_id: str = "standard_dramatic",
    limit: Optional[int] = None,
    manifest: Optional[dict] = None,
    document: Optional[Any] = None,
    target_block_ids: Optional[List[str]] = None,
) -> List[Proposal]:
    """Asks the model to rewrite each flagged action block; never mutates the text."""
    document = document or parse_document(text)
    targets = None
    if target_block_ids is not None:
        if (not isinstance(target_block_ids, list) or not target_block_ids or
                any(not isinstance(item, str) or not item for item in target_block_ids) or
                len(set(target_block_ids)) != len(target_block_ids)):
            raise ValueError('Select one or more distinct action block IDs')
        targets = set(target_block_ids)
        available = {block.id for block in document.blocks if block.role == BlockRole.ACTION}
        if not targets <= available:
            raise ValueError('Selected conditioning block is missing or is not an action block')
    profile = StyleProfileRepository().get_style_profile(profile_id) or STANDARD_DRAMATIC
    proposals: List[Proposal] = []
    attempted = 0

    for block in document.blocks:
        if block.role != BlockRole.ACTION:
            continue
        if targets is not None and block.id not in targets:
            continue
        report = ProseDiagnosticsAnalyzer.analyze(block.text)
        # Explicit author selection can request a bounded review even when the
        # automatic diagnostic has not flagged that particular action block.
        if not report.warnings and targets is None:
            continue
        if limit is not None and attempted >= limit:
            break
        attempted += 1

        request = ProseRewriteRequest(
            request_id=f"cond_{uuid.uuid4().hex[:8]}",
            project_id="story",
            document_id="story",
            base_revision=1,
            target_span_id=block.id,
            original_text=block.text,
            category=SpanCategory.STAGE_ACTION,
            style_profile_id=profile.profile_id,
            **context_fields(manifest),
        )
        prompt = PromptAssembler.assemble(
            request=request,
            diagnostics=report,
            style_profile=profile,
            approved_edits=[],
            reference_passages=[],
            concise_conditioning=True,
        )
        minimum = math.ceil(len(block.text) * MIN_RATIO)
        maximum = math.floor(len(block.text) * MAX_RATIO)
        prompt += (
            "\n\nCONDITIONING DIRECTIVE: Rewrite the paragraph in place. Keep every concrete "
            "fact, character, and action. Preserve who performs each action, where each person "
            "is, and who possesses each object; never transfer an object or reverse an action. "
            "Keep the existing tone and avoid adding events, dialogue, or characters. "
            "A sensory detail is optional and must fit naturally. "
            f"Return exactly one paragraph of {minimum} to {maximum} characters, including "
            f"spaces and punctuation; aim for about {len(block.text)} characters. "
            "If a faithful improvement cannot fit, return the original unchanged. "
            "Return only the paragraph, with no explanation."
        )
        reasons = []
        candidate = ''
        for attempt in range(MAX_CONDITIONING_ATTEMPTS):
            try:
                raw = provider.generate_rewrite(request, prompt)
            except Exception as exc:  # provider/transport failure must not abort the pass
                reason = f'provider error: {exc}'[:180]
                candidate = ''
                reasons.append(reason)
                break
            candidate = _tidy_candidate(block.text, ' '.join(InvariantGate.clean_candidate_text(raw).split()))
            ok, violations, _cleaned = validate_rewrite(candidate, request)
            if not candidate:
                reason = 'empty candidate'
            elif not ok:
                reason = '; '.join(violations)[:160]
            elif candidate == block.text:
                reason = 'unchanged'
            elif _lost_subject(block.text, candidate):
                reason = 'rewrite dropped the described subject'
            else:
                reason = 'ok'
            reasons.append(reason)
            retry = []
            if any(violation.startswith('length ratio ') for violation in violations):
                retry.append(f'Use {minimum}–{maximum} characters.')
            if any(violation.startswith('Possible reversed action:') for violation in violations):
                retry.append('Keep each original action, location, subject, and object owner unchanged.')
            if any(violation == 'Numeric facts changed' for violation in violations):
                retry.append('Retain every original number exactly.')
            if any(violation == 'Possible omitted possessed key; author review required' for violation in violations):
                retry.append('Keep the key and preserve who has it, as in the original.')
            if reason == 'rewrite dropped the described subject':
                retry.append('Keep every original named person in the same role.')
            if reason == 'ok' or attempt + 1 >= MAX_CONDITIONING_ATTEMPTS or not retry:
                break
            prompt += (
                '\n\nREVISION CORRECTION: The previous response failed a check and was not applied. '
                'Rewrite the ORIGINAL passage again. ' + ' '.join(retry) +
                ' Keep all original facts and actions; return only one paragraph.'
            )
        proposals.append(Proposal(block.id, block.line, report.warnings, block.text, candidate,
                                  reason == 'ok', reason, attempt_reasons=reasons,
                                  provider=getattr(provider, 'provider_id', type(provider).__name__),
                                  model_name=getattr(provider, 'model_name', ''),
                                  reasoning_effort=getattr(provider, 'reasoning_effort', '')))

    for proposal in proposals:
        proposal.base_hash = source_hash(text)
    return proposals


def _lost_subject(original: str, candidate: str) -> bool:
    """Conservative name heuristic; sentence-initial function words are not names."""
    common_starters = {'The', 'And', 'But', 'Then', 'She', 'Her', 'His', 'Their',
        'They', 'This', 'That', 'There', 'When', 'While', 'After', 'Before', 'Once',
        'Meanwhile', 'Nearby', 'Inside', 'Outside', 'Under', 'Across', 'Later',
        'Suddenly', 'Now', 'Here', 'From', 'With', 'Without', 'Into', 'Over', 'Only',
        'Every', 'Each', 'Another', 'Both', 'Neither', 'Together'}
    names = {word for word in re.findall(r"\b[A-Z][a-z]{2,}\b", original) if word not in common_starters}
    if not names:
        return False
    return not all(re.search(r'\b' + re.escape(name) + r'\b', candidate, re.I) for name in names)


def _tidy_candidate(original: str, candidate: str) -> str:
    """Removes stray wrapping quotes the model adds when the original had none."""
    text = candidate.strip()
    if text.startswith('"') and not original.lstrip().startswith('"'):
        text = text[1:].lstrip()
    if text.endswith('"') and not original.rstrip().endswith('"'):
        text = text[:-1].rstrip()
    return text


def apply_proposals(text: str, proposals: List[Proposal], approved_ids: Optional[List[str]] = None) -> Tuple[str, int]:
    """Applies accepted proposals one line at a time; returns (text, applied_count)."""
    updated = text
    applied = 0
    approved = set(approved_ids or [])
    if any(p.base_hash and p.base_hash != source_hash(text) for p in proposals if p.block_id in approved):
        raise ValueError('Stale proposal: source revision changed; replan before applying')
    for proposal in proposals:
        if not proposal.accepted or proposal.block_id not in approved:
            continue
        try:
            proposed = _tidy_candidate(proposal.original, proposal.proposed)
            block = parse_document(updated).block_by_id(proposal.block_id)
            if block.text != proposal.original:
                raise ValueError('Original span changed')
            updated = replace_block_text(updated, proposal.block_id, proposed)
            applied += 1
            proposal.reviewed = True
        except (KeyError, ValueError) as exc:
            proposal.accepted = False
            proposal.reason = f"could not apply: {exc}"
    return updated, applied


def _review_html(title: str, proposals: List[Proposal]) -> str:
    rows = []
    for proposal in proposals:
        status = 'author approved' if proposal.reviewed else 'pending author review' if proposal.accepted else f"skipped ({proposal.reason})"
        rows.append(
            "<article>"
            f'<div class="meta">{proposal.line} · {html.escape(status)} · {html.escape("; ".join(proposal.warnings[:2]))}</div>'
            f'<div class="orig">{html.escape(proposal.original)}</div>'
            f'<div class="new">{html.escape(proposal.proposed or "—")}</div>'
            "</article>"
        )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)} - conditioning review</title><style>"
        "body{background:#0b1120;color:#e2e8f0;font-family:ui-sans-serif,system-ui;padding:24px;max-width:1100px;margin:auto}"
        "h1{color:#fbbf24;font-size:20px}article{border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}"
        ".meta{font:11px ui-monospace,Consolas;color:#94a3b8;margin-bottom:6px}"
        ".orig{color:#f87171;text-decoration:line-through;margin:4px 0}"
        ".new{color:#4ade80}"
        "</style></head><body>"
        f"<h1>{html.escape(title)} - prose conditioning proposals</h1>"
        f"<p class=\"meta\">{sum(1 for p in proposals if p.accepted)} eligible for review / {len(proposals)} flagged spans</p>"
        + "".join(rows)
        + "</body></html>"
    )


def _audit(path: Path) -> Dict[str, Any]:
    try:
        report = HTMLFeedbackLoopVerifier.audit_html(path)
        return {
            "converged": report.converged,
            "filter_words": report.metrics.get("filter_words", 0),
            "burstiness_sigma": report.metrics.get("burstiness_sigma", 0.0),
        }
    except Exception as exc:
        return {"converged": False, "error": str(exc)[:160]}


def run_conditioning(
    source_path: Path,
    out_dir: Path,
    provider_type: str = "mock",
    apply: bool = False,
    limit: Optional[int] = None,
    title: Optional[str] = None,
    provider: Optional[Any] = None,
    approved_ids: Optional[List[str]] = None,
    manifest: Optional[dict] = None,
    reviewed_proposals: Optional[List[Proposal]] = None,
) -> Dict[str, Any]:
    source_path = Path(source_path)
    text = source_path.read_bytes().decode('utf-8')
    title = title or source_path.stem
    out = Path(out_dir)
    targets = ('proposals.json','review.html','story.conditioned.md','reader.conditioned.html','report.json')
    if any((out / name).exists() or (out / name).resolve() == source_path.resolve() for name in targets):
        raise FileExistsError('Conditioning output already exists or overlaps the source; choose a new output directory')
    if apply and approved_ids and reviewed_proposals is None:
        raise ValueError('Use a previously generated proposal file for explicit approvals; do not regenerate reviewed text')
    out.mkdir(parents=True, exist_ok=True)

    if reviewed_proposals is not None:
        proposals = reviewed_proposals
        ids = [p.block_id for p in proposals]
        if len(ids) != len(set(ids)) or set(approved_ids or []) - set(ids):
            raise ValueError('Proposal IDs must be unique and every approved ID must exist')
        for p in proposals:
            if p.block_id not in (approved_ids or []):
                continue
            request = ProseRewriteRequest(request_id='review',project_id='story',document_id='story',
                base_revision=1,target_span_id=p.block_id,original_text=p.original,
                category=SpanCategory.STAGE_ACTION, **context_fields(manifest))
            valid, _, _ = validate_rewrite(p.proposed,request)
            if not p.base_hash or not p.accepted or not valid or _lost_subject(p.original,p.proposed):
                raise ValueError('The reviewed proposal is missing evidence or no longer passes validation')
    else:
        provider = provider or create_prose_provider(provider_type)
        proposals = plan_conditioning(text, provider, limit=limit, manifest=manifest)

    result: Dict[str, Any] = {
        "provider": 'reviewed proposal file' if reviewed_proposals is not None else provider_type,
        "flagged": len(proposals),
        "accepted": sum(1 for p in proposals if p.accepted),
        "applied": 0,
        "artifacts": {"proposals": str(out / "proposals.json"), "review": str(out / "review.html")},
    }

    if apply and result["accepted"]:
        updated, applied = apply_proposals(text, proposals, approved_ids=approved_ids)
        result["applied"] = applied
        if not applied:
            result['pending_review'] = sum(p.accepted and not p.reviewed for p in proposals)
        else:
            conditioned = out / "story.conditioned.md"
            conditioned.write_bytes(updated.encode('utf-8'))
        if applied:
            reader = out / "reader.conditioned.html"
            reader.write_text(
                render_reader(parse_document(updated), story_theme(f"{title} (conditioned)")),
                encoding="utf-8",
            )
            audit = _audit(reader)
            result["artifacts"].update({"conditioned": str(conditioned), "reader": str(reader)})
            result["audit"] = audit

            metrics = [
                ProseDiagnosticsAnalyzer.analyze(block.text)
                for block in parse_document(updated).blocks
                if block.role == BlockRole.ACTION
            ]
            result["after"] = {
                "filter_words": sum(m.filter_word_count for m in metrics),
                "emotion_labels": sum(len(m.label_examples) for m in metrics),
                "spans_with_warnings": sum(1 for m in metrics if m.warnings),
                "mean_burstiness": round(sum(m.burstiness_score for m in metrics) / max(1, len(metrics)), 2),
            }

    (out / 'proposals.json').write_text(json.dumps([p.to_dict() for p in proposals], indent=2, ensure_ascii=False), encoding='utf-8')
    (out / 'review.html').write_text(_review_html(title, proposals), encoding='utf-8')
    result['pending_review'] = sum(p.accepted and not p.reviewed for p in proposals)
    (out / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def load_reviewed_proposals(path: Path) -> List[Proposal]:
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('Proposal file must contain a list')
    proposals = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('accepted'), bool):
            raise ValueError('Invalid proposal record')
        attempts = row.get('attempt_reasons', [])
        if not isinstance(attempts, list) or not all(isinstance(reason, str) for reason in attempts):
            raise ValueError('Invalid proposal attempt record')
        proposals.append(Proposal(block_id=row['block_id'],line=row['line'],warnings=row['warnings'],
            original=row['original'],proposed=row['proposed'],accepted=row['accepted'],reason=row['reason'],
            base_hash=row.get('base_hash',''), attempt_reasons=attempts,
            provider=row.get('provider',''), model_name=row.get('model_name',''),
            reasoning_effort=row.get('reasoning_effort','')))
    return proposals


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="narrative_composer.condition", description="Prose conditioning pass")
    parser.add_argument("--file", required=True, help="Story text to condition")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--provider", default="mock", help="mock | codex | api | deepseek | venice")
    parser.add_argument("--limit", type=int, default=None, help="Max flagged spans to attempt")
    parser.add_argument("--apply", action="store_true", help="Write conditioned text and reader")
    parser.add_argument("--title", default=None, help="Title for the conditioned reader")
    parser.add_argument('--approve', action='append', default=[], help='Reviewed block ID to apply (repeat for each reviewed span)')
    parser.add_argument('--proposals', default=None, help='Previously generated and reviewed proposals.json')
    parser.add_argument('--manifest', default=None, help='World snapshot supplying prop and knowledge constraints')
    args = parser.parse_args(argv)

    result = run_conditioning(
        Path(args.file),
        Path(args.out),
        provider_type=args.provider,
        apply=args.apply,
        limit=args.limit,
        title=args.title,
        approved_ids=args.approve,
        manifest=json.loads(Path(args.manifest).read_text(encoding='utf-8')) if args.manifest else None,
        reviewed_proposals=load_reviewed_proposals(Path(args.proposals)) if args.proposals else None,
    )
    print(f"provider:  {result['provider']}")
    print(f"flagged:   {result['flagged']}   eligible for review: {result['accepted']}   applied: {result['applied']}")
    print(f"review:    {result['artifacts']['review']}")
    if result.get("audit"):
        print(f"audit:     {result['audit']}")
    if result.get("after"):
        print(f"after:     {result['after']}")
    if result["artifacts"].get("reader"):
        print(f"reader:    {result['artifacts']['reader']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
