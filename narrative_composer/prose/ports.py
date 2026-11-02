"""
Abstract port interfaces (Protocols) for the Noir Module 1 Prose Engine.
Keeps domain logic fully decoupled from transport, external storage, and concrete models.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from narrative_composer.prose.models import (
    DecisionRecord,
    DecisionType,
    ProseRewriteProposal,
    ProseRewriteRequest,
)


@runtime_checkable
class ModelProviderPort(Protocol):
    """Protocol for AI rewrite engines (Gemini 3.8 Flash, local session, synthetic mock)."""
    
    def generate_rewrite(self, request: ProseRewriteRequest, prompt: str) -> str:
        """Generates candidate prose given a request packet and assembled prompt."""
        ...


@runtime_checkable
class LedgerStorePort(Protocol):
    """Protocol for persisting proposals, append-only revisions, and author decisions."""

    def get_current_revision(self, project_id: str, document_id: str) -> int:
        """Returns the latest revision number for the given document (0 if new)."""
        ...

    def record_proposal(self, proposal: ProseRewriteProposal) -> None:
        """Stores a generated proposal awaiting author decision."""
        ...

    def get_proposal(self, proposal_id: str) -> Optional[ProseRewriteProposal]:
        """Retrieves a proposal by its unique ID."""
        ...

    def commit_decision(
        self,
        proposal: ProseRewriteProposal,
        decision: DecisionType,
        author_text: Optional[str] = None,
        command_id: str = "",
        author_notes: Optional[str] = None,
    ) -> DecisionRecord:
        """
        Commits an accept, reject, or author-edit decision.
        Must be idempotent with respect to command_id and reject stale base revisions.
        """
        ...

    def get_decision_by_command_id(self, command_id: str) -> Optional[DecisionRecord]:
        """Retrieves a committed decision by its command ID (for idempotency checks)."""
        ...

    def list_revisions(self, project_id: str, document_id: str) -> List[DecisionRecord]:
        """Returns the full chronological history of committed revisions for a document."""
        ...


@runtime_checkable
class StyleProfileRepositoryPort(Protocol):
    """Protocol for accessing show-specific style guides and voice rules."""

    def get_style_profile(self, profile_id: str) -> Optional[Any]:
        """Retrieves style configuration for a given profile ID."""
        ...


@runtime_checkable
class ApprovedEditsStorePort(Protocol):
    """Protocol for storing and retrieving author-approved corrections scoped by profile."""

    def add_edit(self, edit: Any) -> None:
        """Stores an approved edit pair."""
        ...

    def retrieve_relevant_edits(
        self, profile_id: str, context_text: str, max_results: int = 3
    ) -> List[Any]:
        """Retrieves top relevant edits strictly isolated within the specified profile."""
        ...
