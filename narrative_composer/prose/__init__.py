"""
Noir Module 1 Prose Engine for Neurosymbolic Narrative Composer.
Headless, deterministic prose conditioning, protected span preservation, and revision ledger.
"""

from narrative_composer.prose.models import (
    SpanCategory,
    DecisionType,
    ProtectedSpan,
    SourceIdentity,
    DocumentIdentity,
    EvidenceSpan,
    ProseDiagnosticReport,
    ProseRewriteRequest,
    ProseRewriteProposal,
    DecisionRecord,
    ProseEngineError,
    MissingIdentityError,
    ProtectedSpanViolationError,
    RevisionConflictError,
    validate_identities,
)
from narrative_composer.prose.protected_spans import ProtectedSpanProtector
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer
from narrative_composer.prose.invariant_gate import InvariantGate
from narrative_composer.prose.composer_bridge import ComposerBridgeAdapter
from narrative_composer.prose.ports import (
    ModelProviderPort,
    LedgerStorePort,
    StyleProfileRepositoryPort,
    ApprovedEditsStorePort,
)
from narrative_composer.prose.ledger import RevisionLedger
from narrative_composer.prose.style_engine import (
    StyleProfile,
    StyleProfileRepository,
    NOIR_DETECTIVE,
    STANDARD_DRAMATIC,
)
from narrative_composer.prose.approved_edits import ApprovedEditPair, ApprovedEditsStore
from narrative_composer.prose.semantic_drive import ReferencePassage, SemanticDrive
from narrative_composer.prose.prompt_assembler import PromptAssembler
from narrative_composer.prose.providers import (
    BaseProseProvider,
    MockProseProvider,
    GeminiFlashProseProvider,
    VeniceProseProvider,
    TransportMode,
    ProviderReceipt,
    ProviderError,
    ProviderConfigurationError,
    ProviderExecutionError,
    create_prose_provider,
)

__version__ = "1.0.0"

__all__ = [
    # Models
    "SpanCategory",
    "DecisionType",
    "ProtectedSpan",
    "SourceIdentity",
    "DocumentIdentity",
    "EvidenceSpan",
    "ProseDiagnosticReport",
    "ProseRewriteRequest",
    "ProseRewriteProposal",
    "DecisionRecord",
    # Exceptions
    "ProseEngineError",
    "MissingIdentityError",
    "ProtectedSpanViolationError",
    "RevisionConflictError",
    # Functions & Validators
    "validate_identities",
    "ProtectedSpanProtector",
    "ProseDiagnosticsAnalyzer",
    "InvariantGate",
    "ComposerBridgeAdapter",
    # Ports & Ledger
    "ModelProviderPort",
    "LedgerStorePort",
    "StyleProfileRepositoryPort",
    "ApprovedEditsStorePort",
    "RevisionLedger",
    # Style & Retrieval
    "StyleProfile",
    "StyleProfileRepository",
    "NOIR_DETECTIVE",
    "STANDARD_DRAMATIC",
    "ApprovedEditPair",
    "ApprovedEditsStore",
    "ReferencePassage",
    "SemanticDrive",
    "PromptAssembler",
    # Providers
    "BaseProseProvider",
    "MockProseProvider",
    "GeminiFlashProseProvider",
    "VeniceProseProvider",
    "TransportMode",
    "ProviderReceipt",
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderExecutionError",
    "create_prose_provider",
]
