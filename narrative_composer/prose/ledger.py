"""
Append-only revision and decision ledger.
Ensures:
- Idempotency via command IDs
- Strict detection and rejection of stale base revisions
- Reversible human/automated decisions
- Serialization to disk for CLI reload and persistence across restarts
"""

import json
import os
import uuid
from typing import Dict, List, Optional
from narrative_composer.prose.models import (
    DecisionRecord,
    DecisionType,
    ProseRewriteProposal,
    RevisionConflictError,
    MissingIdentityError,
)
from narrative_composer.prose.ports import LedgerStorePort


class RevisionLedger(LedgerStorePort):
    """
    In-memory and file-backed append-only revision ledger.
    Does NOT connect to external networks or spawn background processes on import or initialization.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self._proposals: Dict[str, ProseRewriteProposal] = {}
        self._decisions: Dict[str, DecisionRecord] = {}
        self._command_index: Dict[str, str] = {}  # command_id -> decision_id
        self._document_revisions: Dict[str, int] = {}  # f"{project_id}:{document_id}" -> revision int
        self._document_history: Dict[str, List[str]] = {}  # f"{project_id}:{document_id}" -> [decision_ids]

        if self.storage_path and os.path.exists(self.storage_path):
            self._load_from_disk()

    def _doc_key(self, project_id: str, document_id: str) -> str:
        return f"{project_id}:{document_id}"

    def get_current_revision(self, project_id: str, document_id: str) -> int:
        """Returns the latest revision number for the given document (0 if new)."""
        return self._document_revisions.get(self._doc_key(project_id, document_id), 0)

    def record_proposal(self, proposal: ProseRewriteProposal) -> None:
        """Stores a generated proposal awaiting author decision."""
        if not proposal.proposal_id:
            raise MissingIdentityError("Proposal missing proposal_id.")
        self._proposals[proposal.proposal_id] = proposal
        self._persist_if_configured()

    def get_proposal(self, proposal_id: str) -> Optional[ProseRewriteProposal]:
        """Retrieves a proposal by its unique ID."""
        return self._proposals.get(proposal_id)

    def get_decision_by_command_id(self, command_id: str) -> Optional[DecisionRecord]:
        """Retrieves a committed decision by its command ID (for idempotency checks)."""
        if not command_id:
            return None
        dec_id = self._command_index.get(command_id)
        if dec_id:
            return self._decisions.get(dec_id)
        return None

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
        Idempotent: retry with the same command_id returns the existing DecisionRecord.
        Stale check: raises RevisionConflictError if proposal.base_revision != current_revision.
        """
        if not proposal.project_id or not proposal.document_id:
            raise MissingIdentityError("Proposal must include non-empty project_id and document_id.")

        # 1. Idempotency Check
        if command_id:
            existing = self.get_decision_by_command_id(command_id)
            if existing is not None:
                return existing

        # 2. Stale Base Revision Check
        doc_key = self._doc_key(proposal.project_id, proposal.document_id)
        current_rev = self._document_revisions.get(doc_key, 0)
        if proposal.base_revision != current_rev:
            raise RevisionConflictError(
                f"Conflict on document '{proposal.document_id}': proposal targets base revision "
                f"{proposal.base_revision}, but current revision is {current_rev}."
            )

        # 3. Determine Resulting Revision & Final Text
        if decision == DecisionType.ACCEPTED:
            resulting_rev = current_rev + 1
            final_text = proposal.proposed_text
        elif decision == DecisionType.AUTHOR_EDITED:
            if not author_text:
                raise ValueError("author_text is required when decision is AUTHOR_EDITED.")
            resulting_rev = current_rev + 1
            final_text = author_text
        elif decision == DecisionType.REJECTED:
            # Rejection records the decision but does not advance the document text revision
            resulting_rev = current_rev
            final_text = proposal.original_text
        else:
            raise ValueError(f"Unsupported decision type: {decision}")

        # 4. Create Decision Record
        dec_id = f"dec_{uuid.uuid4().hex[:12]}"
        record = DecisionRecord(
            decision_id=dec_id,
            command_id=command_id or dec_id,
            proposal_id=proposal.proposal_id,
            project_id=proposal.project_id,
            document_id=proposal.document_id,
            base_revision=current_rev,
            resulting_revision=resulting_rev,
            decision=decision,
            original_text=proposal.original_text,
            final_text=final_text,
            author_notes=author_notes,
        )

        # 5. Commit to In-Memory Indexes
        self._decisions[dec_id] = record
        if command_id:
            self._command_index[command_id] = dec_id
        self._document_revisions[doc_key] = resulting_rev
        if doc_key not in self._document_history:
            self._document_history[doc_key] = []
        self._document_history[doc_key].append(dec_id)

        # 6. Persist to Disk if Configured
        self._persist_if_configured()

        return record

    def list_revisions(self, project_id: str, document_id: str) -> List[DecisionRecord]:
        """Returns the full chronological history of committed revisions for a document."""
        doc_key = self._doc_key(project_id, document_id)
        dec_ids = self._document_history.get(doc_key, [])
        return [self._decisions[did] for did in dec_ids if did in self._decisions]

    # ========================================================================
    # Persistence Helpers
    # ========================================================================

    def _persist_if_configured(self) -> None:
        if not self.storage_path:
            return

        os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
        payload = {
            "proposals": {k: v.model_dump() for k, v in self._proposals.items()},
            "decisions": {k: v.model_dump() for k, v in self._decisions.items()},
            "command_index": self._command_index,
            "document_revisions": self._document_revisions,
            "document_history": self._document_history,
        }
        temp_path = f"{self.storage_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        # Atomic replace
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)
        os.rename(temp_path, self.storage_path)

    def _load_from_disk(self) -> None:
        if not self.storage_path or not os.path.exists(self.storage_path):
            return

        with open(self.storage_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        self._proposals = {
            k: ProseRewriteProposal.model_validate(v)
            for k, v in payload.get("proposals", {}).items()
        }
        self._decisions = {
            k: DecisionRecord.model_validate(v)
            for k, v in payload.get("decisions", {}).items()
        }
        self._command_index = payload.get("command_index", {})
        self._document_revisions = payload.get("document_revisions", {})
        self._document_history = payload.get("document_history", {})
