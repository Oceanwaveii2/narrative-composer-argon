"""
Protected source spans and invariant verification.
Ensures that prose-only operations cannot alter, drop, or mutate canonical source words,
dialogue utterances, or protected entities (e.g., non-Latin tokens, key props, names).
"""

import re
from typing import List, Tuple
from narrative_composer.prose.models import (
    ProtectedSpan,
    SpanCategory,
    ProtectedSpanViolationError,
)


class ProtectedSpanProtector:
    """Verifies that protected source spans and required tokens remain intact in prose outputs."""

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Collapse redundant whitespace, newlines, and tabs."""
        return " ".join(text.strip().split())

    @classmethod
    def verify_tokens_present(
        cls,
        candidate_text: str,
        required_tokens: List[str],
        case_sensitive: bool = False
    ) -> List[str]:
        """
        Returns a list of missing tokens.
        Preserves support for opaque and non-Latin synthetic tokens (e.g. 'Δt_alpha', 'Zorgon_99').
        """
        missing = []
        search_target = candidate_text if case_sensitive else candidate_text.lower()

        for token in required_tokens:
            token_clean = token.strip()
            if not token_clean:
                continue
            token_search = token_clean if case_sensitive else token_clean.lower()
            
            # Use regex word boundary where applicable, or direct substring for non-ASCII/symbols
            # If the token contains non-word characters (like '-' or Greek letters), use escaped pattern
            escaped = re.escape(token_search)
            # Check if escaped pattern matches anywhere in text
            if not re.search(escaped, search_target):
                missing.append(token_clean)

        return missing

    @classmethod
    def verify_protected_span(
        cls,
        candidate_text: str,
        protected_span: ProtectedSpan,
        case_sensitive: bool = False
    ) -> None:
        """
        Verifies that a single protected span is satisfied in candidate_text.
        Raises ProtectedSpanViolationError on failure.
        """
        # 1. Check required tokens
        missing_tokens = cls.verify_tokens_present(
            candidate_text,
            protected_span.required_tokens,
            case_sensitive=case_sensitive
        )
        if missing_tokens:
            raise ProtectedSpanViolationError(
                f"Protected span '{protected_span.span_id}' ({protected_span.category.value}: \"{protected_span.text}\") "
                f"violation: missing required token(s): {missing_tokens}"
            )

        # 2. For DIALOGUE spans, check canonical phrase preservation
        if protected_span.category == SpanCategory.DIALOGUE:
            norm_span = cls.normalize_whitespace(protected_span.text)
            norm_target = cls.normalize_whitespace(candidate_text)
            
            check_span = norm_span if case_sensitive else norm_span.lower()
            check_target = norm_target if case_sensitive else norm_target.lower()
            
            # Strip outer quotation marks if any
            clean_span = check_span.strip('\'"')
            if clean_span not in check_target:
                raise ProtectedSpanViolationError(
                    f"Protected dialogue span '{protected_span.span_id}' was mutated or omitted: "
                    f"expected intact text '{norm_span}' in proposed prose."
                )

    @classmethod
    def verify_all(
        cls,
        candidate_text: str,
        protected_spans: List[ProtectedSpan],
        case_sensitive: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validates all protected spans. Returns (is_valid, list_of_error_messages).
        """
        errors = []
        for span in protected_spans:
            try:
                cls.verify_protected_span(candidate_text, span, case_sensitive=case_sensitive)
            except ProtectedSpanViolationError as err:
                errors.append(str(err))

        return len(errors) == 0, errors
