"""
Closed-Loop Convergence Harness.
Combines Screenplay AST parsing, deterministic & neurosymbolic invariant linting,
dual-tier recook dispatching, reader HTML compilation, and reverse-DOM verification
into a single self-stabilizing automated convergence loop.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..models.epistemic import EpistemicMatrix, NarrativeFact, EpistemicBelief
from ..models.spatial_fsm import SpatialGraph, PhysicalEntity
from ..models.causal_dag import CausalDAG, StoryBeatNode
from ..parser.fountain_lexer import FountainParser
from ..linter.screenplay_linter import ScreenplayLinter
from ..linter.html_feedback_loop import HTMLFeedbackLoopVerifier, FeedbackLoopAuditReport
from .recook_dispatcher import RecookDispatcher, RecookReport
from .html_compiler import compile_screenplay_html


@dataclass
class ConvergenceIterationReport:
    iteration: int
    rule_violations_detected: int
    tier1_patches_applied: int
    tier2_rewrites_applied: int
    html_audit_converged: bool
    html_audit_hard_errors: int
    html_audit_soft_warnings: int
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class ConvergenceResult:
    converged: bool
    total_iterations: int
    initial_rule_violations: int
    final_rule_violations: int
    total_tier1_patches: int
    total_tier2_rewrites: int
    iteration_reports: List[ConvergenceIterationReport] = field(default_factory=list)
    final_html_report: Optional[FeedbackLoopAuditReport] = None
    screenplay_path: str = ""
    html_path: str = ""
    graph_errors: int = 0
    graph_warnings: int = 0
    graph_review_questions: int = 0
    graph_gate_errors: int = 0
    graph_suggestions: int = 0
    graph_status: str = 'not run'
    artifact_dir: str = ''

    def summary(self) -> str:
        status = "CONVERGED" if self.converged else "FAILED_TO_CONVERGE"
        lines = [
            f"=== CONVERGENCE HARNESS REPORT [{status}] ===",
            f"* Total Iterations Run:       {self.total_iterations}",
            f"* Initial Rule Violations:    {self.initial_rule_violations}",
            f"* Final Rule Violations:      {self.final_rule_violations}",
            f"* Total Tier 1 Patches:       {self.total_tier1_patches}",
            f"* Total Tier 2 Rewrites:      {self.total_tier2_rewrites}",
            f"* Screenplay Target:          {self.screenplay_path}",
            f"* Reader HTML Target:         {self.html_path}",
            f"* Run Artifact Directory:     {self.artifact_dir}",
        ]
        if self.final_html_report:
            lines.extend([
                f"* HTML Reverse Audit:         {'PASS' if self.final_html_report.converged else 'FAIL'}",
                f"  - Total Elements Parsed:    {self.final_html_report.total_elements_parsed}",
                f"  - Total DOM IDs:            {self.final_html_report.total_dom_ids}",
                f"  - Total Nav Links:          {self.final_html_report.total_nav_links}",
                f"  - Burstiness Sigma:         {self.final_html_report.metrics.get('burstiness_sigma', 0.0):.2f}",
                f"  - Filter Words in Prose:    {int(self.final_html_report.metrics.get('filter_words', 0))}",
                f"  - Emotion Labels in Prose:  {int(self.final_html_report.metrics.get('emotion_labels', 0))}",
            ])
        lines.extend([
            f"* Narrative Node Graph ({self.graph_status}):",
            f"  - Graph Errors:             {self.graph_errors}",
            f"  - Graph Warnings:           {self.graph_warnings}",
            f"  - Review Questions:         {self.graph_review_questions}",
            f"  - Blocking Gate Checks:     {self.graph_gate_errors}",
            f"  - Graph Suggestions:        {self.graph_suggestions}",
        ])
        return "\n".join(lines)


class ClosedLoopConvergenceHarness:
    """
    Executes a multi-pass feedback loop until fixpoint convergence:
      Fountain/Markdown -> AST -> Linter -> Recook Dispatcher -> Recompiled HTML -> Reverse-Ingest Audit
    """

    def __init__(
        self,
        manifest_path: str,
        provider_mode: str = "mock",
        max_iterations: int = 5,
    ):
        self.manifest_path = manifest_path
        self.provider_mode = provider_mode
        self.max_iterations = max_iterations

    def _load_manifest_state(self) -> tuple[EpistemicMatrix, SpatialGraph, CausalDAG]:
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        facts = {k: NarrativeFact(**v) for k, v in data.get("facts", {}).items()}
        epistemic = EpistemicMatrix(facts=facts)
        for char, beliefs in data.get("initial_beliefs", {}).items():
            for fact_id, val in beliefs.items():
                epistemic.set_belief(char, fact_id, EpistemicBelief(val))

        props = {k: PhysicalEntity(**v) for k, v in data.get("props", {}).items()}
        spatial = SpatialGraph(
            items=props,
            character_locations=data.get("character_locations", {}),
            room_topology=data.get("room_topology", {}),
        )
        beats = {k: StoryBeatNode(**v) for k, v in data.get("beats", {}).items()}
        dag = CausalDAG(beats=beats)
        return epistemic, spatial, dag

    def run(
        self,
        screenplay_path: Path | str,
        html_out_path: Optional[Path | str] = None,
        in_place: bool = True,
    ) -> ConvergenceResult:
        screenplay_file = Path(screenplay_path)
        if not screenplay_file.exists():
            raise FileNotFoundError(f"Screenplay file not found: {screenplay_file}")

        requested_html = Path(html_out_path).resolve() if html_out_path is not None else None
        if requested_html is not None and requested_html.exists():
            raise FileExistsError('Reader output already exists; choose a new destination')
        if self.max_iterations < 1:
            raise ValueError('At least one convergence iteration is required')
        run_dir = screenplay_file.resolve().parent / 'out' / 'convergence_runs' / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        html_file = None

        iteration_reports: List[ConvergenceIterationReport] = []
        total_tier1 = 0
        total_tier2 = 0
        initial_violations_count = 0
        final_violations_count = 0
        final_html_audit: Optional[FeedbackLoopAuditReport] = None
        converged = False

        script_text = screenplay_file.read_text(encoding='utf-8')
        original_text = script_text
        for iteration in range(1, self.max_iterations + 1):
            ast = FountainParser.parse(script_text)

            epistemic, spatial, _ = self._load_manifest_state()
            linter = ScreenplayLinter(epistemic, spatial)
            violations = linter.lint_full_script(ast)

            if iteration == 1:
                initial_violations_count = len(violations)
            final_violations_count = len(violations)

            tier1_applied = 0
            tier2_applied = 0

            # If rule violations exist, dispatch repairs
            if violations:
                dispatcher = RecookDispatcher(provider_type=self.provider_mode)
                active_props = {k: v.lifecycle.value for k, v in spatial.items.items()}
                dispatch_report = dispatcher.dispatch_all(
                    script_text, violations, active_props=active_props
                )
                tier1_applied = dispatch_report.tier1_patches_applied
                tier2_applied = dispatch_report.tier2_rewrites_applied
                total_tier1 += tier1_applied
                total_tier2 += tier2_applied

                # Update script text with patched version
                script_text = dispatch_report.reconstructed_script

            # Recompile HTML Reader
            html_file = run_dir / f'iteration_{iteration}.html'
            compile_screenplay_html(
                chronology_path=screenplay_file,
                out_file=html_file,
                screenplay_text=script_text,
            )

            # Reverse-ingest and audit HTML DOM
            html_audit = HTMLFeedbackLoopVerifier.audit_html(html_file)
            final_html_audit = html_audit

            hard_errors = [v for v in html_audit.violations if v.severity == "HARD_ERROR"]
            soft_warnings = [v for v in html_audit.violations if v.severity == "SOFT_WARNING"]

            iter_report = ConvergenceIterationReport(
                iteration=iteration,
                rule_violations_detected=len(violations),
                tier1_patches_applied=tier1_applied,
                tier2_rewrites_applied=tier2_applied,
                html_audit_converged=html_audit.converged,
                html_audit_hard_errors=len(hard_errors),
                html_audit_soft_warnings=len(soft_warnings),
                metrics=dict(html_audit.metrics),
            )
            iteration_reports.append(iter_report)

            # Check convergence conditions: 0 rule violations and HTML audit passes with 0 hard errors
            if len(violations) == 0 and html_audit.converged:
                converged = True
                break

            # If violations remain but zero repairs could be applied, stop to avoid looping indefinitely
            if violations and (tier1_applied == 0 and tier2_applied == 0):
                break

        # Milestone 12: Narrative Node Graph Advisory Pass (non-blocking)
        graph_errors = 0
        graph_warnings = 0
        graph_review_questions = 0
        graph_gate_errors = 0
        graph_suggestions = 0
        graph_status = 'not run'
        try:
            from ..graph.pipeline import process_text
            graph_out_dir = run_dir / 'graphs'
            graph_report = process_text(
                text=script_text,
                canon="hot_scoomp_main",
                run_id="convergence_run",
                out_dir=graph_out_dir,
                learn=False,
            )
            g_summary = graph_report.get("summary", {})
            graph_errors = g_summary.get("errors", 0)
            graph_warnings = g_summary.get("warnings", 0)
            graph_review_questions = g_summary.get("review_questions", 0)
            graph_gate_errors = g_summary.get("gate_errors", graph_errors)
            graph_suggestions = g_summary.get("suggestions", 0)
            graph_status = ('failed' if graph_errors else 'pending review' if graph_review_questions else
                            'not modeled' if not g_summary.get('state_instances', 0) else 'passed')
        except Exception as exc:
            import logging
            logging.warning(f"Advisory Narrative Node Graph pass failed: {exc}")
            graph_status = 'failed'

        converged = converged and graph_status == 'passed'
        if in_place and script_text != original_text:
            raise ValueError('Automatic manuscript replacement is disabled; review proposals in the editor')

        if requested_html is not None:
            requested_html.parent.mkdir(parents=True, exist_ok=True)
            with requested_html.open('xb') as output:
                output.write(html_file.read_bytes())
            html_file = requested_html

        return ConvergenceResult(
            converged=converged,
            total_iterations=len(iteration_reports),
            initial_rule_violations=initial_violations_count,
            final_rule_violations=final_violations_count,
            total_tier1_patches=total_tier1,
            total_tier2_rewrites=total_tier2,
            iteration_reports=iteration_reports,
            final_html_report=final_html_audit,
            screenplay_path=str(screenplay_file),
            html_path=str(html_file),
            graph_errors=graph_errors,
            graph_warnings=graph_warnings,
            graph_review_questions=graph_review_questions,
            graph_gate_errors=graph_gate_errors,
            graph_suggestions=graph_suggestions,
            graph_status=graph_status,
            artifact_dir=str(run_dir),
        )
