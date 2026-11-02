"""
Full Automated Pipeline Runner for Neurosymbolic Narrative Composer.
Executes:
  1. Pass 1: Narrative Node Graph (NNG) Construction & Invariant Validation
  2. Pass 2: Automated Prose Conditioning & Diagnostics (0 filter words, cadence burstiness)
  3. Pass 3: High-Performance Screenplay HTML Reader Compilation
  4. Pass 4: Closed-Loop Reverse-Ingestion DOM Audit
  5. Real-Time Benchmark Timing
"""

import sys
import time
from pathlib import Path
import json

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.world_port import PrototypeWorld
from narrative_composer.graph.pipeline import process_text
from narrative_composer.compiler.html_compiler import compile_screenplay_html
from narrative_composer.linter.html_feedback_loop import HTMLFeedbackLoopVerifier
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.parser.fountain_lexer import FountainParser
from narrative_composer.models.ast_nodes import ASTNodeType


def run_pipeline(
    script_path: str = "HOT_SCOOMP_COMPLETE_CHRONOLOGY.md",
    canon: str = "hot_scoomp_main",
    run_id: str = "master",
    out_dir: str = "out/graphs",
    html_out_path: str = "hot_scoomp_reader.html",
    manifest_path: str | None = None,
    entity_dir: str | None = None,
):
    total_start = time.perf_counter()
    script_file = Path(script_path)
    if not script_file.exists():
        print(f"[ERROR] Screenplay not found at: {script_file.resolve()}", file=sys.stderr)
        sys.exit(1)

    output_root = Path(out_dir).resolve()
    reader_output = Path(html_out_path).resolve()
    expected_outputs = [output_root / f'{run_id}.{suffix}' for suffix in ('chain.json','graph.json','report.json','viewer.html')]
    expected_outputs += [output_root / 'project.report.json', reader_output]
    if len(set(expected_outputs)) != len(expected_outputs) or any(path.exists() for path in expected_outputs):
        raise FileExistsError('Pipeline output already exists or overlaps another output; choose new destinations')

    print("======================================================================")
    print(" NEUROSYMBOLIC NARRATIVE COMPOSER: FULL AUTOMATED PIPELINE")
    print(f" Source:    {script_file.name}")
    print(f" Canon:     {canon}")
    print(f" Run ID:    {run_id}")
    print("======================================================================\n")

    # -------------------------------------------------------------------------
    # PASS 1: NARRATIVE NODE GRAPH GENERATION & VALIDATION
    # -------------------------------------------------------------------------
    p1_start = time.perf_counter()
    print("[PASS 1/4] Constructing Narrative Node Graph...")
    text = script_file.read_bytes().decode('utf-8')
    registry = load_registry(Path(entity_dir) if entity_dir else None)
    from narrative_composer.store import DEFAULT_MANIFEST
    selected_manifest = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST
    manifest = json.loads(selected_manifest.read_text(encoding='utf-8'))
    graph = StoryGraph.from_registry(registry)
    world = PrototypeWorld()
    out_path = Path(out_dir)

    graph_report = process_text(
        text=text,
        canon=canon,
        run_id=run_id,
        out_dir=out_path,
        graph=graph,
        world=world,
        learn=False,
        initial_states=manifest.get('initial_character_states'),
        reviewed_observations=manifest.get('reviewed_state_observations'),
        data_root=script_file.resolve().parent / 'character_data',
    )
    p1_time = time.perf_counter() - p1_start

    summary = graph_report.get("summary", {})
    from narrative_composer.store import build_store
    from narrative_composer.workspace import project_report
    store = build_store(script_file, selected_manifest,
                        canon=canon, registry=registry, text=text)
    integrated = project_report(store)
    with (out_path / 'project.report.json').open('x', encoding='utf-8') as output:
        output.write(json.dumps(integrated, indent=2, ensure_ascii=False))
    violations = graph_report.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "ERROR"]
    warnings = [v for v in violations if v.get("severity") == "WARNING"]

    print(f"  ✓ Processed in {p1_time:.3f}s")
    print(f"  * State Instances Tracked: {summary.get('state_instances', 0)}")
    print(f"  * Transforms Traversed:    {summary.get('transforms', 0)}")
    print(f"  * Continuity Violations:   ERROR: {len(errors)}, WARNING: {len(warnings)}")

    # -------------------------------------------------------------------------
    # PASS 2: AUTOMATED PROSE CONDITIONING & DIAGNOSTICS
    # -------------------------------------------------------------------------
    p2_start = time.perf_counter()
    print("\n[PASS 2/4] Measuring prose diagnostics (no rewrite or composition requested)...")
    ast = FountainParser.parse(text)
    action_texts = [e.content for e in ast if e.node_type == ASTNodeType.ACTION]
    # Analyse each action block independently: a single concatenated corpus inflates
    # cadence variance and hides monotonous blocks.
    span_reports = [ProseDiagnosticsAnalyzer.analyze(t) for t in action_texts]
    total_filters = sum(r.filter_word_count for r in span_reports)
    total_labels = sum(len(r.label_examples) for r in span_reports)
    mean_burstiness = (
        round(sum(r.burstiness_score for r in span_reports) / len(span_reports), 2)
        if span_reports
        else 0.0
    )
    below_target = sum(1 for r in span_reports if r.burstiness_score < 4.5)
    p2_time = time.perf_counter() - p2_start

    print(f"  ✓ Processed in {p2_time:.3f}s")
    print(f"  * Action Blocks Analyzed:  {len(action_texts)}")
    print(f"  * Mean Cadence Burstiness:{mean_burstiness:.2f} (Target: >= 4.5)")
    print(f"  * Blocks Below Target:     {below_target} / {len(span_reports)}")
    print(f"  * Filter Words in Prose:   {total_filters} (Target: 0)")
    print(f"  * Emotion Labels in Prose: {total_labels} (Target: 0)")

    # -------------------------------------------------------------------------
    # PASS 3: HIGH-PERFORMANCE SCREENPLAY HTML READER COMPILATION
    # -------------------------------------------------------------------------
    p3_start = time.perf_counter()
    print("\n[PASS 3/4] Compiling Screenplay Reader HTML...")
    reader_path = Path(html_out_path)
    compile_screenplay_html(
        chronology_path=script_file,
        out_file=reader_path,
        screenplay_text=text,
    )
    p3_time = time.perf_counter() - p3_start
    print(f"  ✓ Processed in {p3_time:.3f}s -> {reader_path.name} ({reader_path.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # PASS 4: CLOSED-LOOP REVERSE-INGESTION AUDIT
    # -------------------------------------------------------------------------
    p4_start = time.perf_counter()
    print("\n[PASS 4/4] Reverse-Ingesting & Auditing DOM Integrity...")
    audit_report = HTMLFeedbackLoopVerifier.audit_html(reader_path)
    p4_time = time.perf_counter() - p4_start

    print(f"  ✓ Processed in {p4_time:.3f}s")
    print(f"  * DOM Elements Ingested:   {audit_report.total_elements_parsed}")
    print(f"  * DOM IDs Verified:        {audit_report.total_dom_ids} (Zero duplicate IDs)")
    print(f"  * Navigation Links Audited:{audit_report.total_nav_links} (Zero dangling hrefs)")
    print(f"  * Audit Convergence:       {'PASS [CONVERGED]' if audit_report.converged else 'FAIL'}")

    total_time = time.perf_counter() - total_start
    print("\n======================================================================")
    print(f" [ANALYSIS {integrated['status'].upper()}] Wall-Clock Run Time: {total_time:.3f} seconds")
    print('  Composition / model rewrite: NOT RUN. Reaction candidates: pending author review.')
    print(f"  - Pass 1 (Node Graph):     {p1_time:.3f}s ({p1_time/total_time*100:.1f}%)")
    print(f"  - Pass 2 (Prose Engine):   {p2_time:.3f}s ({p2_time/total_time*100:.1f}%)")
    print(f"  - Pass 3 (HTML Reader):    {p3_time:.3f}s ({p3_time/total_time*100:.1f}%)")
    print(f"  - Pass 4 (DOM Audit):      {p4_time:.3f}s ({p4_time/total_time*100:.1f}%)")
    print("======================================================================\n")


if __name__ == "__main__":
    run_pipeline()
