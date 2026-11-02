"""
Command-Line Interface (CLI) for Neurosymbolic Narrative Composer.
Expanded with Noir Module 1 Prose Engine commands:
- Script linting against epistemic & spatial invariants
- Prose diagnostics (filter words, label syntax, cadence, sensory budgeting)
- Prose conditioning & rewrite via Gemini 3.8 Flash / Session / Mock
- Reversible proposal review & append-only revision ledger
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .models.epistemic import EpistemicMatrix, NarrativeFact, EpistemicBelief
from .models.spatial_fsm import SpatialGraph, PhysicalEntity
from .models.causal_dag import CausalDAG, StoryBeatNode
from .models.ast_nodes import ASTNodeType
from .parser.fountain_lexer import FountainParser
from .linter.screenplay_linter import ScreenplayLinter
from .linter.rules import LinterRuleEngine

# Prose Engine imports
from .prose.diagnostics import ProseDiagnosticsAnalyzer
from .prose.models import DecisionType, ProseRewriteRequest, ProtectedSpan, SpanCategory
from .prose.style_engine import StyleProfileRepository, STANDARD_DRAMATIC
from .prose.approved_edits import ApprovedEditsStore
from .prose.semantic_drive import SemanticDrive
from .prose.prompt_assembler import PromptAssembler
from .prose.providers import create_prose_provider
from .prose.invariant_gate import InvariantGate
from .prose.ledger import RevisionLedger


# Force UTF-8 on Windows consoles where available
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_manifest(manifest_path: str):
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
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
        room_topology=data.get("room_topology", {})
    )
    beats = {k: StoryBeatNode(**v) for k, v in data.get("beats", {}).items()}
    dag = CausalDAG(beats=beats)

    return epistemic, spatial, dag


def cmd_status(manifest_path: str):
    epistemic, spatial, dag = load_manifest(manifest_path)
    print(f"\n=== MANIFEST STATUS: {os.path.basename(manifest_path)} ===")
    print(f"* Total Narrative Facts: {len(epistemic.facts)}")
    print(f"* Total Props Tracked:   {len(spatial.items)}")
    print(f"* Total Story Beats:     {len(dag.beats)}")
    print("\n--- DAG EXECUTION ORDER ---")
    for beat in dag.get_topological_order():
        status = "[DONE]" if beat.is_completed else "[PENDING]"
        prereqs = f"(Prereqs: {', '.join(beat.prerequisite_beat_ids)})" if beat.prerequisite_beat_ids else "(Root Beat)"
        print(f"  {beat.beat_order}. {status} {beat.beat_id} {prereqs}")

    print("\n--- PROP INVENTORY ---")
    for item_id, item in spatial.items.items():
        charges = f" (Charges: {item.charges_remaining})" if item.charges_remaining is not None else ""
        holder = f" [Held by {item.held_by}]" if item.held_by else ""
        print(f"  * {item.name}: Lifecycle={item.lifecycle.value.upper()}, Room={item.room_id}{charges}{holder}")


def cmd_lint(manifest_path: str, script_path: str):
    epistemic, spatial, dag = load_manifest(manifest_path)
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, "rb") as f:
        original_bytes = f.read()
    script_text = original_bytes.decode('utf-8')

    print(f"\n=== LINTING SCRIPT: {os.path.basename(script_path)} ===")
    ast = FountainParser.parse(script_text)
    print(f"* Parsed {len(ast)} Screenplay AST elements.")

    linter = ScreenplayLinter(epistemic, spatial)
    violations = linter.lint_full_script(ast)
    rule_count = len([name for name in dir(LinterRuleEngine) if name.startswith("check_")])

    if not violations:
        print(f"\n[PASS] ZERO CONTINUITY VIOLATIONS DETECTED. Script passes all {rule_count} lint rules!")
        print("       (Graph-level G1-G7 checks are separate - run --graph-build for those.)")
    else:
        print(f"\n[FAIL] FOUND {len(violations)} CONTINUITY VIOLATIONS:")
        for idx, v in enumerate(violations, start=1):
            print(f"\n[{idx}] {v.rule_id} at line {v.line_number}:")
            print(f"    OFFENDING TEXT: \"{v.offending_text}\"")
            print(f"    DIAGNOSTIC:     {v.diagnostic_message}")
            print(f"    INSTRUCTION:    {v.repair_instruction}")


# ============================================================================
# Prose Engine CLI Commands
# ============================================================================

def cmd_prose_diagnose(script_path: str):
    """Runs deterministic prose diagnostics across all action blocks in a script."""
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, "r", encoding="utf-8") as f:
        script_text = f.read()

    ast = FountainParser.parse(script_text)
    action_elements = [e for e in ast if e.node_type == ASTNodeType.ACTION]

    print(f"\n=== PROSE DIAGNOSTIC REPORT: {os.path.basename(script_path)} ===")
    print(f"* Total Screenplay Elements: {len(ast)}")
    print(f"* Total Action Blocks Scanned: {len(action_elements)}\n")

    total_filters = 0
    total_labels = 0
    total_sensory = 0
    spans_with_warnings = 0
    burstiness_scores = []

    for elem in action_elements:
        report = ProseDiagnosticsAnalyzer.analyze(elem.content, span_id=f"L{elem.line_number}")
        total_filters += report.filter_word_count
        if report.label_syntax_detected:
            total_labels += len(report.label_examples)
        total_sensory += report.sensory_details_count
        burstiness_scores.append(report.burstiness_score)

        if report.warnings:
            spans_with_warnings += 1
            print(f"[Line {elem.line_number}] \"{elem.content[:60]}...\"")
            for w in report.warnings:
                print(f"  * {w}")
            print()

    avg_burstiness = round(sum(burstiness_scores) / len(burstiness_scores), 2) if burstiness_scores else 0.0

    print("--- DIAGNOSTIC SUMMARY ---")
    print(f"* Action Spans with Warnings: {spans_with_warnings} / {len(action_elements)}")
    print(f"* Total Observer Filter Words: {total_filters}")
    print(f"* Total Emotion Label Flags:   {total_labels}")
    print(f"* Total Concrete Sensory Anchors: {total_sensory}")
    print(f"* Average Cadence Burstiness:  {avg_burstiness:.2f} (Target >= 4.5)")
    if spans_with_warnings == 0:
        print("\n[PASS] All prose blocks satisfy the stylistic and sensory budget standards!")


def cmd_prose_rewrite(
    target_text: str,
    profile_id: str = "standard_dramatic",
    mode: str = "mock",
    ledger_path: Optional[str] = None,
    manifest_path: Optional[str] = None,
):
    """Executes closed-loop prose conditioning on a target span."""
    # 1. Lookup style profile
    repo = StyleProfileRepository()
    profile = repo.get_style_profile(profile_id)
    if profile is None:
        profile = STANDARD_DRAMATIC
        print(f"Unknown style profile {profile_id!r}; using {profile.profile_id}.")
    print(f"\n=== EXECUTING PROSE REWRITE (Profile: {profile.profile_id}, Mode: {mode.upper()}) ===")

    # 2. Extract props and epistemic state from manifest if available
    active_props = {}
    epistemic_scope = {}
    if manifest_path and os.path.exists(manifest_path):
        epistemic, spatial, _ = load_manifest(manifest_path)
        active_props = {k: v.lifecycle.value for k, v in spatial.items.items()}
        # InvariantGate.verify_epistemic_bounds only inspects entries beginning with
        # "unknown_", so scope must list facts the character has not yet learned.
        unlearned = (
            EpistemicBelief.UNKNOWN,
            EpistemicBelief.COGNITIVE_SUPPRESSION,
            EpistemicBelief.AMNESIA_BLANK,
        )
        epistemic_scope = {
            char: [
                f"unknown_{fact_id}"
                for fact_id, belief in beliefs.items()
                if belief in unlearned
            ]
            for char, beliefs in epistemic.beliefs.items()
        }
        epistemic_scope = {char: facts for char, facts in epistemic_scope.items() if facts}

    # 3. Build ProseRewriteRequest
    prot_spans = [
        ProtectedSpan(
            span_id="prot_core",
            category=SpanCategory.GENERAL,
            text=target_text,
        )
    ]
    req = ProseRewriteRequest(
        request_id=f"cli_req_{os.getpid()}",
        project_id="cli_project",
        document_id="cli_doc",
        base_revision=0,
        target_span_id="span_target",
        original_text=target_text,
        protected_spans=prot_spans,
        active_props=active_props,
        character_epistemic_scope=epistemic_scope,
        style_profile_id=profile.profile_id,
    )

    # 4. Diagnostics before
    diag_before = ProseDiagnosticsAnalyzer.analyze(target_text, span_id="cli_target")

    # 5. Retrieve approved edits & assemble prompt
    edits_store = ApprovedEditsStore()
    approved_edits = edits_store.retrieve_relevant_edits(profile.profile_id, target_text)
    prompt = PromptAssembler.assemble(
        request=req,
        diagnostics=diag_before,
        style_profile=profile,
        approved_edits=approved_edits,
        reference_passages=[],
    )

    # 6. Generate via provider
    provider = create_prose_provider(mode=mode)
    raw_output = provider.generate_rewrite(req, prompt)

    # 7. Invariant Gate validation
    proposal, violations = InvariantGate.create_verified_proposal(
        candidate_text=raw_output,
        request=req,
        diagnostics_before=diag_before,
        model_provider=provider.model_name,
    )

    print("\n--- REWRITE PROPOSAL ---")
    print(f"PROPOSAL ID: {proposal.proposal_id}")
    print(f"PROTECTED WORDS VERIFIED: {proposal.protected_words_verified}")
    print(f"EPISTEMIC VERIFIED:       {proposal.epistemic_verified}")
    if violations:
        print(f"VIOLATIONS FLAGGED: {len(violations)}")
        for v in violations:
            print(f"  * [VIOLATION] {v}")
    print(f"\nPROPOSED TEXT:\n{proposal.proposed_text}\n")

    # 8. Store in ledger if configured
    if ledger_path:
        ledger = RevisionLedger(storage_path=ledger_path)
        ledger.record_proposal(proposal)
        print(f"[STORED] Proposal saved to ledger: {ledger_path}")

    return proposal


def cmd_prose_review(
    proposal_id: str,
    decision: str,
    ledger_path: str,
    author_text: Optional[str] = None,
):
    """Reviews and commits an accept, reject, or author-edit decision to the ledger."""
    if not os.path.exists(ledger_path):
        print(f"Error: Ledger file not found at {ledger_path}", file=sys.stderr)
        sys.exit(1)

    ledger = RevisionLedger(storage_path=ledger_path)
    proposal = ledger.get_proposal(proposal_id)
    if not proposal:
        print(f"Error: Proposal '{proposal_id}' not found in ledger.", file=sys.stderr)
        sys.exit(1)

    dec_enum = DecisionType(decision.lower())
    record = ledger.commit_decision(
        proposal=proposal,
        decision=dec_enum,
        author_text=author_text,
        command_id=f"cli_cmd_{proposal_id}_{decision}",
    )

    print(f"\n=== COMMITTED DECISION: {decision.upper()} ===")
    print(f"* Decision ID: {record.decision_id}")
    print(f"* Base Revision: {record.base_revision} -> Resulting Revision: {record.resulting_revision}")
    print(f"* Final Text: {record.final_text}")


def cmd_recook(
    manifest_path: str,
    script_path: str,
    out_path: Optional[str] = None,
    mode: str = "mock"
):
    """Executes the automated dual-tier recook dispatcher on a screenplay script."""
    from .compiler.recook_dispatcher import RecookDispatcher
    epistemic, spatial, _ = load_manifest(manifest_path)
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    with open(script_path, "rb") as f:
        original_bytes = f.read()
    script_text = original_bytes.decode('utf-8')

    ast = FountainParser.parse(script_text)
    linter = ScreenplayLinter(epistemic, spatial)
    violations = linter.lint_full_script(ast)

    print(f"\n=== RECOOK ENGINE: {os.path.basename(script_path)} ===")
    print(f"* Initial Violations Detected: {len(violations)}")

    if not violations:
        print("[PASS] Script is already clean. No recook required!")
        return

    dispatcher = RecookDispatcher(provider_type=mode)
    active_props = {k: v.lifecycle.value for k, v in spatial.items.items()}
    report = dispatcher.dispatch_all(script_text, violations, active_props=active_props)

    print(f"* Tier 1 Surgical Patches Applied: {report.tier1_patches_applied}")
    print(f"* Tier 2 Neural Rewrites Applied:   {report.tier2_rewrites_applied}")
    print(f"* Pending author-review proposals:  {len(report.pending_proposals)}")
    for p in report.patch_records:
        print(f"  [{p.tier.value.upper()}] Line {p.line_number} ({p.rule_id}): {p.description}")

    if out_path:
        target_out = Path(out_path)
        if target_out.resolve() == Path(script_path).resolve() or target_out.exists():
            raise ValueError('Recook preview must use a new output path; the source is preserved')
        target_out.write_bytes(original_bytes)
        print(f"\n[PREVIEW] Unchanged source copy written to: {target_out}")
    print("[REVIEW] Original screenplay unchanged; use the editor to review individual proposals.")
    return report


def cmd_auto_converge(
    manifest_path: str,
    script_path: str,
    html_out: Optional[str] = None,
    max_iterations: int = 5,
    mode: str = "mock",
):
    """Executes the closed-loop convergence harness until fixpoint."""
    from .compiler.convergence_harness import ClosedLoopConvergenceHarness

    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== AUTO-CONVERGE CLOSED LOOP HARNESS ===")
    print(f"* Manifest:       {manifest_path}")
    print(f"* Screenplay:     {script_path}")
    print(f"* Max Iterations: {max_iterations}")
    print(f"* Provider Mode:  {mode}\n")

    harness = ClosedLoopConvergenceHarness(
        manifest_path=manifest_path,
        provider_mode=mode,
        max_iterations=max_iterations,
    )
    result = harness.run(
        screenplay_path=script_path,
        html_out_path=html_out,
        in_place=True,
    )
    print(result.summary())
    if not result.converged:
        print("\n[FAIL] Closed loop failed to achieve fixpoint convergence within max iterations.")
        sys.exit(1)
    else:
        advisory = ""
        if getattr(result, "graph_errors", 0):
            advisory = (
                f" Advisory graph errors still open: {result.graph_errors}"
                " (run --graph-build for the report)."
            )
        print(f"\n[SUCCESS] Linter fixpoint convergence achieved: 0 rule violations, 0 HTML errors.{advisory}")


def cmd_graph_build(
    script_path: str,
    canon: str = "hot_scoomp_main",
    run_id: Optional[str] = None,
    out_dir: str = "out/graphs",
    annotate_path: Optional[str] = None,
    learn: bool = True,
):
    from pathlib import Path
    from narrative_composer.graph.registry import load_registry
    from narrative_composer.graph.graph import StoryGraph
    from narrative_composer.graph.world_port import PrototypeWorld
    from narrative_composer.graph.pipeline import process_text

    p = Path(script_path)
    if not p.exists():
        print(f"Error: Script file not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    text = p.read_text(encoding="utf-8")
    actual_run_id = run_id or p.stem

    graph = StoryGraph.from_registry(load_registry())
    world = PrototypeWorld()

    print(f"\n=== COOKING NARRATIVE NODE GRAPH: {actual_run_id} ({canon}) ===")
    report = process_text(
        text=text,
        canon=canon,
        run_id=actual_run_id,
        out_dir=Path(out_dir),
        graph=graph,
        world=world,
        learn=learn,
        annotations_path=annotate_path,
    )

    summary = report.get("summary", {})
    print(f"* State Instances: {summary.get('state_instances', 0)}")
    print(f"* Transforms:      {summary.get('transforms', 0)}")
    print(f"* Violations:      ERROR: {summary.get('errors', 0)}, WARNING: {summary.get('warnings', 0)}, INFO: {summary.get('infos', 0)}")
    print(f"* Suggestions:     {summary.get('suggestions', 0)}")
    print(f"* Output files:    {out_dir}/{actual_run_id}.chain.json, {out_dir}/{actual_run_id}.graph.json, {out_dir}/{actual_run_id}.report.json")


def cmd_graph_export(
    spec: str,
    canon: str = "hot_scoomp_main",
    out_dir: str = "out/graphs",
):
    from pathlib import Path
    from narrative_composer.graph.registry import load_registry
    from narrative_composer.graph.graph import StoryGraph
    from narrative_composer.graph.world_port import PrototypeWorld
    from narrative_composer.graph.export import export_standalone

    parts = spec.split(":")
    if len(parts) < 2:
        print(f"Error: --graph-export-standalone requires ENTITY:FROM[:TO], got {spec!r}", file=sys.stderr)
        sys.exit(1)

    entity = parts[0]
    from_slug = parts[1]
    to_slug = parts[2] if len(parts) > 2 else None

    graph = StoryGraph.from_registry(load_registry())
    world = PrototypeWorld()

    data = export_standalone(
        graph=graph,
        entity=entity,
        from_state_slug=from_slug,
        to_state_slug=to_slug,
        canon=canon,
        world=world,
    )

    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    suffix = f"{from_slug}__{to_slug}" if to_slug else from_slug
    target_file = out_p / f"{entity}_{suffix}.seed.json"
    target_file.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"* Exported standalone seed to {target_file}")


def cmd_graph_promote(entity_id: str):
    from pathlib import Path
    import json
    from narrative_composer.graph.discover import DEFAULT_AUTO_DIR
    source = DEFAULT_AUTO_DIR / f"{entity_id}.json"
    if not source.exists():
        print(f"Error: Auto-discovered entity {entity_id!r} not found at {source}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(source.read_text(encoding="utf-8"))
    data.setdefault("attributes", {})["provisional"] = False
    data["attributes"]["origin"] = "promoted"
    dest = DEFAULT_AUTO_DIR.parent / f"{entity_id}.json"
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    source.unlink()
    print(f"* Promoted entity {entity_id!r} (moved from auto/ to {dest})")


def cmd_graph_reject(entity_id: str):
    from pathlib import Path
    import json
    from narrative_composer.graph.discover import DEFAULT_AUTO_DIR
    target = DEFAULT_AUTO_DIR / f"{entity_id}.json"
    if not target.exists():
        print(f"Error: Auto-discovered entity {entity_id!r} not found at {target}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["status"] = "deprecated"
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"* Rejected entity {entity_id!r} (deprecated in {target})")


def main():
    parser = argparse.ArgumentParser(description="Neurosymbolic Narrative Composer & Prose Engine CLI")
    parser.add_argument("--manifest", help="Path to manifest JSON file")
    parser.add_argument("--status", action="store_true", help="Display manifest status and DAG topology")
    parser.add_argument("--lint", help="Path to script markdown or fountain file to lint")
    parser.add_argument("--recook", help="Path to script file to automatically patch and recook")
    parser.add_argument("--auto-converge", help="Path to script file to run closed-loop convergence on")
    parser.add_argument("--max-iterations", type=int, default=5, help="Maximum convergence iterations (default: 5)")
    parser.add_argument("--html-out", help="Output path for compiled reader HTML (defaults to hot_scoomp_reader.html)")
    parser.add_argument("--out", help="Output path for recooked script (defaults to in-place)")

    # Prose Engine commands
    parser.add_argument("--prose-diagnose", help="Path to script file to run prose diagnostics on")
    parser.add_argument("--prose-rewrite", action="store_true", help="Execute prose conditioning on text")
    parser.add_argument("--target-text", help="Text to rewrite")
    parser.add_argument("--profile", default="standard_dramatic", help="Style profile ID (default: standard_dramatic)")
    parser.add_argument("--mode", default="mock", choices=["mock", "codex", "session", "api", "deepseek", "venice"], help="Provider mode (standalone CLI defaults to offline mock)")
    parser.add_argument("--ledger", help="Path to ledger JSON file for persistence")
    parser.add_argument("--prose-review", action="store_true", help="Review a saved proposal")
    parser.add_argument("--proposal-id", help="Proposal ID to review")
    parser.add_argument("--decision", choices=["accepted", "rejected", "author_edited"], help="Decision type")
    parser.add_argument("--author-text", help="Author modified text for author_edited decision")

    # Narrative Node Graph (NNG) commands
    parser.add_argument("--graph-build", help="Path to script file to run narrative node graph pipeline on")
    parser.add_argument("--canon", default="hot_scoomp_main", help="Canon universe (default: hot_scoomp_main)")
    parser.add_argument("--run-id", help="Run identifier (default: script file stem)")
    parser.add_argument("--graph-out", default="out/graphs", help="Output directory for graph artifacts (default: out/graphs)")
    parser.add_argument("--graph-annotate", help="Path to annotation JSON file to ingest into graph")
    parser.add_argument("--graph-export-standalone", help="Export standalone seed format: ENTITY:FROM[:TO]")
    parser.add_argument("--no-learn", action="store_true", help="Discover new characters/states in-memory only without saving to config/graph/characters/auto/")
    parser.add_argument("--graph-promote", help="Promote an auto-discovered entity by canonical entity ID")
    parser.add_argument("--graph-reject", help="Reject/deprecate an auto-discovered entity by canonical entity ID")

    args = parser.parse_args()

    if args.status:
        if not args.manifest:
            print("Error: --status requires --manifest", file=sys.stderr)
            sys.exit(1)
        cmd_status(args.manifest)
    elif args.lint:
        if not args.manifest:
            print("Error: --lint requires --manifest", file=sys.stderr)
            sys.exit(1)
        cmd_lint(args.manifest, args.lint)
    elif args.recook:
        if not args.manifest:
            print("Error: --recook requires --manifest", file=sys.stderr)
            sys.exit(1)
        cmd_recook(args.manifest, args.recook, out_path=args.out, mode=args.mode)
    elif args.auto_converge:
        if not args.manifest:
            print("Error: --auto-converge requires --manifest", file=sys.stderr)
            sys.exit(1)
        cmd_auto_converge(
            manifest_path=args.manifest,
            script_path=args.auto_converge,
            html_out=args.html_out,
            max_iterations=args.max_iterations,
            mode=args.mode,
        )
    elif args.prose_diagnose:
        cmd_prose_diagnose(args.prose_diagnose)
    elif args.prose_rewrite:
        if not args.target_text:
            print("Error: --prose-rewrite requires --target-text", file=sys.stderr)
            sys.exit(1)
        cmd_prose_rewrite(
            target_text=args.target_text,
            profile_id=args.profile,
            mode=args.mode,
            ledger_path=args.ledger,
            manifest_path=args.manifest,
        )
    elif args.prose_review:
        if not args.proposal_id or not args.decision or not args.ledger:
            print("Error: --prose-review requires --proposal-id, --decision, and --ledger", file=sys.stderr)
            sys.exit(1)
        cmd_prose_review(
            proposal_id=args.proposal_id,
            decision=args.decision,
            ledger_path=args.ledger,
            author_text=args.author_text,
        )
    elif args.graph_build:
        cmd_graph_build(
            script_path=args.graph_build,
            canon=args.canon,
            run_id=args.run_id,
            out_dir=args.graph_out,
            annotate_path=args.graph_annotate,
            learn=not args.no_learn,
        )
    elif args.graph_export_standalone:
        cmd_graph_export(
            spec=args.graph_export_standalone,
            canon=args.canon,
            out_dir=args.graph_out,
        )
    elif args.graph_promote:
        cmd_graph_promote(args.graph_promote)
    elif args.graph_reject:
        cmd_graph_reject(args.graph_reject)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
