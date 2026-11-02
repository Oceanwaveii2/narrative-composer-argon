"""Display unverified story observations without weakening internal gates."""

REVIEW_QUESTION_RULES = frozenset({'G2_CUE_STATE_MISMATCH', 'G8_UNVERIFIED_EVENT'})


def present_diagnostic(item: dict) -> dict:
    result = dict(item)
    if result.get('source') == 'graph' and result.get('rule_id') in REVIEW_QUESTION_RULES:
        result.update(severity='WARNING', classification='author_review_question',
                      gate_severity=item.get('gate_severity', item.get('severity')),
                      requires_author_review=True)
    return result
