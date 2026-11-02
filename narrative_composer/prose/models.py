"""
Core domain models and contracts for the Noir Module 1 Prose Engine.
Strict adherence to:
- Immutable identities and cryptographic hashes
- Protected word boundaries
- Versioned proposal & revision contracts
- Pure domain models with zero I/O or network side-effects on import
"""

from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


# ============================================================================
# Domain Exceptions
# ============================================================================

class ProseEngineError(Exception):
    """Base exception for all prose engine domain errors."""
    pass


class MissingIdentityError(ProseEngineError):
    """Raised when required project, document, proposal, or revision identities are missing or mismatched."""
    pass


class ProtectedSpanViolationError(ProseEngineError):
    """Raised when a prose operation mutates, drops, or alters a protected source word or token."""
    pass


class RevisionConflictError(ProseEngineError):
    """Raised when an operation targets a stale or conflicting base revision."""
    pass


# ============================================================================
# Enums
# ============================================================================

class SpanCategory(str, Enum):
    DIALOGUE = "dialogue"
    PERFORMANCE_DELIVERY = "delivery"
    STAGE_ACTION = "action"
    SCENE_SETTING = "setting"
    INTERNAL_MONOLOGUE = "monologue"
    GENERAL = "general"


class DecisionType(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AUTHOR_EDITED = "author_edited"


# ============================================================================
# Identity & Evidence Models
# ============================================================================

class SourceIdentity(BaseModel):
    """Identifies an immutable source media file or upstream draft."""
    source_id: str
    locator: str
    source_hash: str  # SHA-256 of the source artifact


class DocumentIdentity(BaseModel):
    """Identifies the target project and document."""
    project_id: str
    document_id: str


class ProtectedSpan(BaseModel):
    """A canonical source span that cannot be mutated by prose operations."""
    span_id: str
    category: SpanCategory
    text: str
    content_hash: str = ""
    required_tokens: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash and self.text:
            self.content_hash = hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()
        if not self.required_tokens and self.text:
            # Extract basic words/tokens if none explicitly provided
            # Split by whitespace and strip basic punctuation
            tokens = [t.strip('.,!?;:"()[]{}') for t in self.text.split()]
            self.required_tokens = [t for t in tokens if t]


class EvidenceSpan(BaseModel):
    """Source-linked evidence linking a span to original media or screenplay beat."""
    span_id: str
    source_id: str
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    speaker: Optional[str] = None
    canonical_words: str
    performed_sound: Optional[str] = None
    claims: List[str] = Field(default_factory=list)


# ============================================================================
# Diagnostics & Proposals
# ============================================================================

class ProseDiagnosticReport(BaseModel):
    """Rule-based diagnostics for filter words, label syntax, and cadence."""
    span_id: str
    filter_word_count: int = 0
    filter_words_found: List[str] = Field(default_factory=list)
    label_syntax_detected: bool = False
    label_examples: List[str] = Field(default_factory=list)
    average_sentence_length: float = 0.0
    burstiness_score: float = 0.0
    sensory_details_count: int = 0
    psychic_distance_estimate: int = 2
    warnings: List[str] = Field(default_factory=list)


class ProseRewriteRequest(BaseModel):
    """Versioned request to rewrite or condition a target span."""
    request_id: str
    project_id: str
    document_id: str
    base_revision: int
    target_span_id: str
    original_text: str
    category: SpanCategory = SpanCategory.STAGE_ACTION
    source_identity: Optional[SourceIdentity] = None
    protected_spans: List[ProtectedSpan] = Field(default_factory=list)
    permitted_facts: List[str] = Field(default_factory=list)
    character_epistemic_scope: Dict[str, List[str]] = Field(default_factory=dict)
    active_props: Dict[str, str] = Field(default_factory=dict)
    target_psychic_distance: int = 2
    style_profile_id: str = "hot_scoomp_tv14"


class ProseRewriteProposal(BaseModel):
    """A generated proposal for author review."""
    proposal_id: str
    request_id: str
    project_id: str
    document_id: str
    base_revision: int
    target_span_id: str
    proposed_text: str
    original_text: str = ''
    semantic_status: str = 'pending author review'
    validation_errors: List[str] = Field(default_factory=list)
    diagnostics_before: Optional[ProseDiagnosticReport] = None
    diagnostics_after: Optional[ProseDiagnosticReport] = None
    protected_words_verified: bool = False
    epistemic_verified: bool = False
    model_provider: str = "mock"
    model_name: str = "synthetic-v1"
    generation_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DecisionRecord(BaseModel):
    """An immutable, append-only record of a human or automated decision."""
    decision_id: str
    command_id: str  # For idempotency
    proposal_id: str
    project_id: str
    document_id: str
    base_revision: int
    resulting_revision: int
    decision: DecisionType
    original_text: str
    final_text: str
    author_notes: Optional[str] = None
    applied_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ============================================================================
# Identity Verification Helper
# ============================================================================

def validate_identities(request: ProseRewriteRequest, proposal: ProseRewriteProposal) -> None:
    """Ensures proposal exactly matches request identities."""
    if not request.project_id or not proposal.project_id:
        raise MissingIdentityError("Missing project_id in request or proposal.")
    if not request.document_id or not proposal.document_id:
        raise MissingIdentityError("Missing document_id in request or proposal.")
    if request.project_id != proposal.project_id:
        raise MissingIdentityError(
            f"Project identity mismatch: {request.project_id} != {proposal.project_id}"
        )
    if request.document_id != proposal.document_id:
        raise MissingIdentityError(
            f"Document identity mismatch: {request.document_id} != {proposal.document_id}"
        )
    if request.base_revision != proposal.base_revision:
        raise MissingIdentityError(
            f"Base revision mismatch: {request.base_revision} != {proposal.base_revision}"
        )
    if request.target_span_id != proposal.target_span_id:
        raise MissingIdentityError(
            f"Target span mismatch: {request.target_span_id} != {proposal.target_span_id}"
        )
