"""
Compiler package for Neurosymbolic Narrative Composer.
"""

from .context_projector import ContextProjector
from .composer_engine import NarrativeComposerEngine
from .recook_dispatcher import (
    RecookDispatcher,
    SurgicalPatcher,
    ProseRecooker,
    DispatchTier,
    RecookReport,
    PatchRecord,
)
from .html_compiler import compile_screenplay_html
from .convergence_harness import (
    ClosedLoopConvergenceHarness,
    ConvergenceResult,
    ConvergenceIterationReport,
)

__all__ = [
    "ContextProjector",
    "NarrativeComposerEngine",
    "RecookDispatcher",
    "SurgicalPatcher",
    "ProseRecooker",
    "DispatchTier",
    "RecookReport",
    "PatchRecord",
    "compile_screenplay_html",
    "ClosedLoopConvergenceHarness",
    "ConvergenceResult",
    "ConvergenceIterationReport",
]
