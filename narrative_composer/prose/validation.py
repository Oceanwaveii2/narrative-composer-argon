"""Shared mechanical rewrite gate. Semantic approval always belongs to review."""
import hashlib
import re
from narrative_composer.prose.invariant_gate import InvariantGate
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer

MIN_REWRITE_RATIO = 0.5
MAX_REWRITE_RATIO = 2.2


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def context_fields(manifest: dict | None) -> dict:
    if not manifest:
        return {}
    return {
        'active_props': {key: prop['lifecycle'] for key, prop in manifest.get('props', {}).items()},
        'permitted_facts': [f['canonical_text'] for f in manifest.get('facts', {}).values()],
        'character_epistemic_scope': {
            char: ['unknown_' + token.replace(' ', '_')
                   for fid, fact in manifest.get('facts', {}).items() if beliefs.get(fid, 0) == 0
                   for token in fact.get('embargo_tokens', [])]
            for char, beliefs in manifest.get('initial_beliefs', {}).items()},
    }


def validate_rewrite(candidate, request, *, allow_style_change=True):
    ok, errors, cleaned = InvariantGate.audit_rewrite(candidate, request)
    original = request.original_text
    ratio = len(cleaned) / max(1, len(original))
    if not MIN_REWRITE_RATIO <= ratio <= MAX_REWRITE_RATIO:
        errors.append(f'length ratio {ratio:.2f}')
    # Conservative contradiction sentinels, not an entailment or factuality model.
    for left, right in [('lock', 'open'), ('stay', 'leave'), ('alive', 'dead'), ('enter', 'exit')]:
        def present(word, text):
            forms = {'leave': r'leav(?:e|es|ing)|left', 'stay': r'stay(?:s|ed|ing)?',
                     'lock': r'lock(?:s|ed|ing)?', 'open': r'open(?:s|ed|ing)?',
                     'enter':r'enter(?:s|ed|ing)?', 'exit':r'exit(?:s|ed|ing)?'}
            return bool(re.search(r'\b(?:' + forms.get(word, re.escape(word)) + r')\b', text, re.I))
        if ((present(left, original) and not present(left, cleaned) and present(right, cleaned)) or
            (present(right, original) and not present(right, cleaned) and present(left, cleaned))):
            errors.append(f'Possible reversed action: {left}/{right}; author review required')
    if re.findall(r'\b\d+(?:\.\d+)?\b', original) != re.findall(r'\b\d+(?:\.\d+)?\b', cleaned):
        errors.append('Numeric facts changed')
    # A narrow omission sentinel for an explicitly held key. It does not prove
    # that ownership or any other prop/action has been preserved.
    if (re.search(r'\bwith\s+(?:the|a|an)\s+key\b', original, re.I) and
            not re.search(r'\bkey\b', cleaned, re.I)):
        errors.append('Possible omitted possessed key; author review required')
    # A narrow Chinese group-subject sentinel, not a general semantic check.
    group_subjects = ('大家', '众人', '所有人', '大伙')
    if any(term in original for term in group_subjects) and not any(term in cleaned for term in group_subjects):
        errors.append('Possible dropped group subject; author review required')
    if allow_style_change:
        before, after = ProseDiagnosticsAnalyzer.analyze(original), ProseDiagnosticsAnalyzer.analyze(cleaned)
        if after.filter_word_count > before.filter_word_count or len(after.label_examples) > len(before.label_examples):
            errors.append('Rewrite introduced filter words or emotion labels')
    return not errors, errors, cleaned
