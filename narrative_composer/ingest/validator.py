"""
Deterministic anti-quote and anti-leak validator for behavioral extractions.
Rejects:
1. N-gram verbatim quote overlaps (>= 5 words) against source transcripts.
2. Source namedrops and meta references (e.g. 'Kardashian', 'Boondocks').
3. Out-of-bounds or invalid evidence timestamp spans.
"""

import re
import string
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from narrative_composer.ingest.schemas import BehavioralTrait, SceneObservation


class ValidationReport(BaseModel):
    """Result of deterministic validation on a SceneObservation."""
    is_valid: bool
    source_id: str
    scene_id: str
    error_count: int
    errors: List[str] = Field(default_factory=list)
    passed_traits_count: int = 0


class ExtractionValidator:
    """
    Deterministic validator ensuring extracted traits represent abstract
    behavioral mechanics rather than lazy transcript quotation or namedropping.
    """

    DEFAULT_BANNED_SOURCE_TOKENS: Set[str] = {
        "kardashian",
        "kardashians",
        "boondocks",
        "granddad",
        "scoomp",
        "hot scoomp",
        "american dad",
        "kim",
        "kourtney",
        "khloe",
        "charlie",
        "riley",
        "huey",
    }

    def __init__(
        self,
        n_gram_quote_limit: int = 5,
        banned_tokens: Optional[Set[str]] = None,
    ):
        self.n_gram_quote_limit = n_gram_quote_limit
        self.banned_tokens = set(banned_tokens or self.DEFAULT_BANNED_SOURCE_TOKENS)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowers and strips punctuation into word tokens."""
        clean = text.lower()
        # Replace punctuation with spaces
        for ch in string.punctuation:
            clean = clean.replace(ch, " ")
        return [w for w in clean.split() if w]

    def find_ngram_quote_overlap(
        self,
        candidate_text: str,
        transcript_text: str,
    ) -> Optional[str]:
        """
        Checks whether candidate_text contains any contiguous sequence of >= N words
        found in the transcript. Returns matching phrase if found, else None.
        """
        c_tokens = self._tokenize(candidate_text)
        t_tokens = self._tokenize(transcript_text)
        t_text_joined = " " + " ".join(t_tokens) + " "

        n = self.n_gram_quote_limit
        if len(c_tokens) < n or len(t_tokens) < n:
            return None

        for i in range(len(c_tokens) - n + 1):
            ngram = " ".join(c_tokens[i : i + n])
            if f" {ngram} " in t_text_joined:
                return ngram

        return None

    def find_banned_namedrop(self, candidate_text: str) -> Optional[str]:
        """
        Checks for exact word-boundary matches of forbidden source tokens.
        """
        lower = candidate_text.lower()
        for token in self.banned_tokens:
            pattern = rf"\b{re.escape(token)}\b"
            if re.search(pattern, lower):
                return token
        return None

    def validate(
        self,
        observation: SceneObservation,
        scene_data: Dict[str, Any],
        full_episode_transcript: Optional[str] = None,
    ) -> ValidationReport:
        """
        Validates an entire SceneObservation against the scene transcript
        and optional full episode transcript.
        """
        errors: List[str] = []
        passed_count = 0

        # Transcript text to check against (scene transcript + optional full transcript)
        scene_transcript = scene_data.get("transcript", "")
        reference_transcript = (
            f"{scene_transcript} {full_episode_transcript or ''}".strip()
        )

        if 'start' not in scene_data or 'end' not in scene_data:
            errors.append('MISSING_AUTHORITATIVE_WINDOW: source scene must supply start/end')
        w_start = scene_data.get('start', 0)
        w_end = scene_data.get('end', 0)
        if (observation.window_start, observation.window_end) != (w_start, w_end):
            errors.append('WINDOW_IDENTITY_MISMATCH: model window differs from source scene')
        for key in ('scene_id', 'source_id'):
            if key in scene_data and getattr(observation, key) != scene_data[key]:
                errors.append(f'{key.upper()}_MISMATCH: generated provenance differs from source')

        for char_obs in observation.characters:
            for trait in char_obs.all_traits():
                trait_desc = f"[{char_obs.character_id}.{trait.category}]: '{trait.trait}'"

                # 1. Check for banned source namedrops
                banned_hit = self.find_banned_namedrop(trait.trait)
                if banned_hit:
                    errors.append(
                        f"NAMEDROP_VIOLATION: Trait {trait_desc} contains banned source token '{banned_hit}'."
                    )
                    continue

                if trait.example_paraphrase:
                    banned_para = self.find_banned_namedrop(trait.example_paraphrase)
                    if banned_para:
                        errors.append(
                            f"NAMEDROP_VIOLATION: Example paraphrase in {trait_desc} contains banned source token '{banned_para}'."
                        )
                        continue

                # 2. Check for verbatim n-gram quotes
                quote_hit = self.find_ngram_quote_overlap(trait.trait, reference_transcript)
                if quote_hit:
                    errors.append(
                        f"QUOTE_LEAK_VIOLATION: Trait {trait_desc} copies verbatim phrase from transcript: '{quote_hit}'."
                    )
                    continue

                if trait.example_paraphrase:
                    quote_para = self.find_ngram_quote_overlap(trait.example_paraphrase, reference_transcript)
                    if quote_para:
                        errors.append(
                            f"QUOTE_LEAK_VIOLATION: Example paraphrase in {trait_desc} copies verbatim phrase: '{quote_para}'."
                        )
                        continue

                # 3. Check timestamp bounds (allow 1.0s leeway for frame cuts)
                if trait.evidence_start < w_start or trait.evidence_end > w_end:
                    errors.append(
                        f"TIMESTAMP_OUT_OF_BOUNDS: Trait {trait_desc} evidence [{trait.evidence_start:.1f}s -> {trait.evidence_end:.1f}s] "
                        f"falls outside scene window [{w_start:.1f}s -> {w_end:.1f}s]."
                    )
                    continue

                if trait.evidence_end <= trait.evidence_start:
                    errors.append(
                        f"INVALID_TIMESTAMP_RANGE: Trait {trait_desc} end time ({trait.evidence_end}) <= start time ({trait.evidence_start})."
                    )
                    continue

                passed_count += 1

        is_valid = len(errors) == 0 and passed_count > 0

        return ValidationReport(
            is_valid=is_valid,
            source_id=observation.source_id,
            scene_id=observation.scene_id,
            error_count=len(errors),
            errors=errors,
            passed_traits_count=passed_count,
        )
