"""
Schema-bound behavioral extraction module.
Orchestrates LLM calls (via Venice or local session) to extract
abstracted kinematics, idiolect, status moves, and rationalizations,
gated by the deterministic ExtractionValidator.
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional

from narrative_composer.ingest.schemas import SceneObservation
from narrative_composer.ingest.validator import ExtractionValidator, ValidationReport


class ExtractionError(Exception):
    """Raised when extraction fails or cannot be repaired."""
    pass


class BehavioralExtractor:
    """
    Extracts abstract behavioral traits from scene packages using LLM reasoning
    under strict schema constraints and deterministic anti-quote validation.
    """

    def __init__(
        self,
        llm_caller: Callable[[str], str],
        validator: Optional[ExtractionValidator] = None,
        max_repairs: int = 2,
    ):
        self.llm_caller = llm_caller
        self.validator = validator or ExtractionValidator()
        self.max_repairs = max_repairs

    @staticmethod
    def _clean_json_response(raw_text: str) -> str:
        """Strips markdown code fences and cleans raw text into valid JSON."""
        text = raw_text.strip()
        # Extract from ```json ... ``` if present
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()
        return text

    def build_extraction_prompt(
        self,
        scene: Dict[str, Any],
        source_id: str,
        target_characters: Optional[List[str]] = None,
        repair_errors: Optional[List[str]] = None,
    ) -> str:
        """
        Builds the strict schema-bound prompt for behavioral extraction.
        """
        s_id = scene.get("scene_id", "scene_000")
        w_start = scene.get("start", 0.0)
        w_end = scene.get("end", 0.0)
        transcript = scene.get("transcript", "").strip()

        schema_json = json.dumps(SceneObservation.model_json_schema(), indent=2)

        prompt_lines = [
            "You are a master character dramatist and kinematic movement analyst.",
            "Analyze the following scene and extract REUSABLE BEHAVIORAL MECHANICS for the characters.",
            "",
            "CRITICAL CONSTRAINTS (STRICTLY ENFORCED BY DETERMINISTIC LINTER):",
            "1. NO QUOTED LINES: Never copy phrases (>= 5 words) from the dialogue transcript.",
            "   Translate spoken lines into abstract vocal/rhetorical techniques (e.g. 'vocal fry on vowel endings', 'using medical terms to justify extreme vanity').",
            "2. NO SOURCE NAMEDROPS: Never use words like 'Kardashian', 'Boondocks', 'American Dad', 'Granddad', 'Scoomp', or celebrity names in the trait text.",
            "3. BEHAVIORAL MECHANICS ONLY: Describe what the body and voice DO as reproducible acting techniques.",
            f"4. EVIDENCE TIMESTAMPS: Every trait must have 'evidence_start' and 'evidence_end' strictly within [{w_start:.1f}s -> {w_end:.1f}s].",
            "",
            f"SCENE INFORMATION:",
            f"- Source ID: {source_id}",
            f"- Scene ID: {s_id}",
            f"- Time Window: [{w_start:.1f}s to {w_end:.1f}s] (Duration: {w_end - w_start:.1f}s)",
        ]

        if target_characters:
            prompt_lines.append(f"- Focus Characters: {', '.join(target_characters)}")

        prompt_lines.extend([
            "",
            "SCENE DIALOGUE TRANSCRIPT:",
            f'"{transcript}"' if transcript else "[Instrumental / Physical Action Scene]",
            "",
            "OUTPUT FORMAT:",
            "Respond with ONLY a JSON object conforming strictly to this JSON Schema:",
            schema_json,
        ])

        if repair_errors:
            prompt_lines.extend([
                "",
                "PREVIOUS ATTEMPT FAILED DETERMINISTIC VALIDATION WITH THESE EXACT ERRORS:",
                *[f" - {err}" for err in repair_errors],
                "Fix these specific violations! Remove quoted phrases, strip namedrops, and fix timestamps.",
            ])

        return "\n".join(prompt_lines)

    def extract_scene(
        self,
        scene: Dict[str, Any],
        source_id: str,
        target_characters: Optional[List[str]] = None,
        full_episode_transcript: Optional[str] = None,
    ) -> SceneObservation:
        """
        Extracts, validates, and auto-repairs a SceneObservation.
        """
        repair_errors: Optional[List[str]] = None
        last_raw_response: str = ""

        for attempt in range(self.max_repairs + 1):
            prompt = self.build_extraction_prompt(
                scene=scene,
                source_id=source_id,
                target_characters=target_characters,
                repair_errors=repair_errors,
            )

            raw_response = self.llm_caller(prompt)
            last_raw_response = raw_response

            try:
                cleaned_json = self._clean_json_response(raw_response)
                data = json.loads(cleaned_json)
                obs = SceneObservation.model_validate(data)
            except Exception as err:
                repair_errors = [f"JSON_SCHEMA_PARSE_ERROR: Failed to parse output into SceneObservation: {err}"]
                continue

            # Deterministic Anti-Quote & Timestamp Validation
            report = self.validator.validate(
                observation=obs,
                scene_data=dict(scene, source_id=source_id),
                full_episode_transcript=full_episode_transcript,
            )

            if report.is_valid:
                return obs

            repair_errors = report.errors

        raise ExtractionError(
            f"Extraction failed validation after {self.max_repairs} repair attempts:\n"
            + "\n".join(repair_errors or [])
            + f"\nLast raw output was:\n{last_raw_response[:400]}"
        )
