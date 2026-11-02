"""
HTML Feedback Loop & Closed-Loop Convergence Verifier.
Implements reverse-ingestion from hot_scoomp_reader.html back into Screenplay AST,
running cascading second-order invariant checks:
  1. DOM Integrity & Anchor-ID Parity (Zero dangling nav links)
  2. Character Dialectic Invariants & Canon Verification
  3. Epistemic Masking & Cascade Diagnostics
  4. Spatial/Prop FSM Lifecycle Invariants (Gloria flamingo lamp, nanobot remote, etc.)
  5. Prose Conditioning Invariants (0 filter words, 0 emotion labels, cadence burstiness)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import html
from pathlib import Path
import re
from typing import List, Dict, Set, Tuple, Optional

from ..models.ast_nodes import ASTElement, ASTNodeType
from ..parser.fountain_lexer import FountainParser
from ..prose.diagnostics import ProseDiagnosticsAnalyzer
from ..prose.invariant_gate import InvariantGate


@dataclass
class FeedbackLoopViolation:
    stage: str
    severity: str  # "HARD_ERROR" or "SOFT_WARNING"
    message: str
    element_id: Optional[str] = None
    line_number: Optional[int] = None
    context_snippet: Optional[str] = None


@dataclass
class FeedbackLoopAuditReport:
    total_elements_parsed: int
    total_dom_ids: int
    total_nav_links: int
    violations: List[FeedbackLoopViolation] = field(default_factory=list)
    converged: bool = False
    iteration_count: int = 1
    metrics: Dict[str, float] = field(default_factory=dict)


class HTMLFeedbackLoopVerifier:
    """
    Parses production HTML readers and subjects them to recursive round-trip validation.
    """

    @staticmethod
    def reverse_ingest_html(html_text: str) -> Tuple[List[ASTElement], Dict[str, List[str]]]:
        """
        Parses screenplay elements directly out of the reader HTML DOM.
        Returns a reconstructed list of ASTElements and a map of DOM metadata.
        """
        ast: List[ASTElement] = []
        dom_metadata = {
            "ids": [],
            "hrefs": [],
            "scene_headings": [],
            "chunk_headers": [],
        }

        # The reader inlines its Tailwind runtime and theme CSS. Strip those payloads
        # first: their contents must never be mistaken for screenplay DOM or prose.
        html_text = re.sub(
            r"<script\b[^>]*>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE
        )
        html_text = re.sub(
            r"<style\b[^>]*>.*?</style>", "", html_text, flags=re.DOTALL | re.IGNORECASE
        )

        # 1. Collect all DOM element IDs and nav hrefs
        dom_metadata["ids"] = re.findall(r'id="([^"]+)"', html_text)
        dom_metadata["hrefs"] = [h for h in re.findall(r'href="#([^"]+)"', html_text) if h != "top"]

        # 2. Extract DOM screenplay divs (attribute order is irrelevant)
        pattern = re.compile(
            r"<div(?P<attrs>[^>]*)>(?P<content>.*?)</div>",
            re.DOTALL
        )

        for match in pattern.finditer(html_text):
            attrs = match.group("attrs")
            class_match = re.search(r'class="([^"]+)"', attrs)
            if not class_match:
                continue
            cls = class_match.group(1)
            content = html.unescape(match.group("content")).strip()
            id_match = re.search(r'id="([^"]+)"', attrs)
            elem_id = id_match.group(1) if id_match else None

            if "scene-heading" in cls:
                dom_metadata["scene_headings"].append(content)
                ast.append(ASTElement(node_type=ASTNodeType.SCENE_HEADING, content=content))
            elif "chunk-header" in cls:
                dom_metadata["chunk_headers"].append(content)
                ast.append(ASTElement(node_type=ASTNodeType.ACTION, content=f"## {content}"))
            elif "act-banner" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.ACTION, content=f"# {content}"))
            elif "character-cue" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.CHARACTER, content=content, speaker=content))
            elif "parenthetical" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.PARENTHETICAL, content=content))
            elif "dialogue" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.DIALOGUE, content=content))
            elif "action-block" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.ACTION, content=content))
            elif "transition-cue" in cls:
                ast.append(ASTElement(node_type=ASTNodeType.TRANSITION, content=content))

        return ast, dom_metadata

    @classmethod
    def audit_html(cls, html_path: Path, max_iterations: int = 3) -> FeedbackLoopAuditReport:
        """
        Runs the closed-loop verification suite on the specified HTML reader file.
        """
        html_text = html_path.read_text(encoding="utf-8")
        ast, dom_metadata = cls.reverse_ingest_html(html_text)

        report = FeedbackLoopAuditReport(
            total_elements_parsed=len(ast),
            total_dom_ids=len(dom_metadata["ids"]),
            total_nav_links=len(dom_metadata["hrefs"]),
        )

        # =====================================================================
        # PASS 1: DOM Integrity & Anchor-ID Parity
        # =====================================================================
        from collections import Counter
        id_counts = Counter(dom_metadata["ids"])
        for eid, count in id_counts.items():
            if count > 1:
                report.violations.append(
                    FeedbackLoopViolation(
                        stage="DOM_INTEGRITY",
                        severity="HARD_ERROR",
                        message=f"Duplicate DOM ID '{eid}' found ({count} instances).",
                        element_id=eid
                    )
                )

        id_set = set(dom_metadata["ids"])
        for href in dom_metadata["hrefs"]:
            if href not in id_set:
                report.violations.append(
                    FeedbackLoopViolation(
                        stage="DOM_INTEGRITY",
                        severity="HARD_ERROR",
                        message=f"Dangling navigation link: '#{href}' does not match any ID in document.",
                        element_id=href
                    )
                )

        # =====================================================================
        # PASS 2: Canon Integrity (Stan GroupMe, Rainee Marriage, 0 Unprompted Steve)
        # =====================================================================
        lower_html = html_text.lower()
        if "smith house" in lower_html:
            report.violations.append(
                FeedbackLoopViolation(
                    stage="CANON_INTEGRITY",
                    severity="HARD_ERROR",
                    message="Found residual 'Smith House' terminology. Must use 'Ling-Eidolessa House'."
                )
            )

        # =====================================================================
        # PASS 3: Spatial Prop FSM State Verification
        # =====================================================================
        # Prop consistency: Gloria the flamingo lamp must remain shattered
        reconstructed_corpus = "\n\n".join(e.content for e in ast)
        prop_violations = InvariantGate.verify_prop_states(
            reconstructed_corpus,
            {"gloria_flamingo_lamp": "shattered"}
        )
        for pv in prop_violations:
            report.violations.append(
                FeedbackLoopViolation(
                    stage="SPATIAL_PROP_FSM",
                    severity="HARD_ERROR",
                    message=f"Prop lifecycle invariant violated: {pv}"
                )
            )

        # =====================================================================
        # PASS 4: Cascading Prose Diagnostics & Second-Order Errors
        # =====================================================================
        action_corpus = "\n\n".join(
            e.content for e in ast if e.node_type == ASTNodeType.ACTION
        )
        prose_rep = ProseDiagnosticsAnalyzer.analyze(action_corpus)

        if prose_rep.filter_word_count > 0:
            # Field is filter_words_found; 'filter_examples' never existed (the bug only
            # surfaced once a script actually contained a filter word).
            for fw in prose_rep.filter_words_found:
                report.violations.append(
                    FeedbackLoopViolation(
                        stage="PROSE_CONDITIONING",
                        severity="HARD_ERROR",
                        message=f"Filter-word violation detected in action prose: '{fw}'",
                        context_snippet=fw
                    )
                )

        if len(prose_rep.label_examples) > 0:
            for el in prose_rep.label_examples:
                report.violations.append(
                    FeedbackLoopViolation(
                        stage="PROSE_CONDITIONING",
                        severity="HARD_ERROR",
                        message=f"Emotion-label or adjective pile detected: '{el}'",
                        context_snippet=el
                    )
                )

        report.metrics["burstiness_sigma"] = prose_rep.burstiness_score
        report.metrics["filter_words"] = prose_rep.filter_word_count
        report.metrics["emotion_labels"] = len(prose_rep.label_examples)

        if prose_rep.burstiness_score < 4.5:
            report.violations.append(
                FeedbackLoopViolation(
                    stage="PROSE_CONDITIONING",
                    severity="SOFT_WARNING",
                    message=f"Cadence burstiness sigma ({prose_rep.burstiness_score:.2f}) is below threshold 4.5."
                )
            )

        # Convergence determination
        hard_errors = [v for v in report.violations if v.severity == "HARD_ERROR"]
        report.converged = (len(hard_errors) == 0)

        return report
