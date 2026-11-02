"""
Unit tests for Milestone 2: Schema-bound behavioral extraction and deterministic anti-quote validation.
"""

import json
import unittest
from unittest.mock import MagicMock

from narrative_composer.ingest.extract import BehavioralExtractor, ExtractionError
from narrative_composer.ingest.schemas import (
    BehavioralTrait,
    CharacterObservation,
    SceneObservation,
)
from narrative_composer.ingest.validator import ExtractionValidator


class TestExtractionSchemasAndValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ExtractionValidator(n_gram_quote_limit=5)
        self.sample_scene = {
            "scene_id": "scene_002",
            "start": 5.0,
            "end": 20.0,
            "transcript": "It is such bullshit that this is illegal. Not really, I'm putting used jello shots and petroleum in your ass. Whatever it takes to keep up with the Kardashians.",
        }

    def test_schema_valid_creation(self):
        trait = BehavioralTrait(
            category="kinematics",
            trait="Exaggerated lumbar lordosis stance, shifting weight to one hip while looking bored.",
            evidence_start=6.0,
            evidence_end=10.0,
            example_paraphrase="She casually glances away while adjusting her posture.",
        )
        char_obs = CharacterObservation(
            character_id="christ_kardashia",
            kinematics=[trait],
        )
        scene_obs = SceneObservation(
            scene_id="scene_002",
            source_id="kardashian_inflate",
            window_start=5.0,
            window_end=20.0,
            characters=[char_obs],
        )
        self.assertEqual(scene_obs.total_trait_count(), 1)
        data = scene_obs.model_dump()
        reloaded = SceneObservation.model_validate(data)
        self.assertEqual(reloaded.scene_id, "scene_002")

    def test_schema_invalid_timestamps_raises(self):
        with self.assertRaises(ValueError):
            BehavioralTrait(
                category="kinematics",
                trait="Invalid trait",
                evidence_start=15.0,
                evidence_end=10.0,  # End before start
            )

    def test_validator_rejects_ngram_quote_leak(self):
        # Contains a 6-word verbatim quote from transcript: "putting used jello shots and petroleum in"
        bad_trait = BehavioralTrait(
            category="rationalization",
            trait="She is putting used jello shots and petroleum in her body for vanity.",
            evidence_start=8.0,
            evidence_end=12.0,
        )
        obs = SceneObservation(
            scene_id="scene_002",
            source_id="kardashian_inflate",
            window_start=5.0,
            window_end=20.0,
            characters=[CharacterObservation(character_id="christ_kardashia", rationalization_patterns=[bad_trait])],
        )
        report = self.validator.validate(obs, self.sample_scene)
        self.assertFalse(report.is_valid)
        self.assertEqual(report.error_count, 1)
        self.assertIn("QUOTE_LEAK_VIOLATION", report.errors[0])
        self.assertIn("putting used jello shots and petroleum in", report.errors[0])

    def test_validator_rejects_source_namedrop(self):
        bad_trait = BehavioralTrait(
            category="idiolect",
            trait="Speaks in an unbothered vocal fry typical of a Kardashian influencer.",
            evidence_start=6.0,
            evidence_end=10.0,
        )
        obs = SceneObservation(
            scene_id="scene_002",
            source_id="kardashian_inflate",
            window_start=5.0,
            window_end=20.0,
            characters=[CharacterObservation(character_id="christ_kardashia", idiolect=[bad_trait])],
        )
        report = self.validator.validate(obs, self.sample_scene)
        self.assertFalse(report.is_valid)
        self.assertEqual(report.error_count, 1)
        self.assertIn("NAMEDROP_VIOLATION", report.errors[0])
        self.assertIn("kardashian", report.errors[0].lower())

    def test_validator_rejects_out_of_bounds_timestamps(self):
        bad_trait = BehavioralTrait(
            category="kinematics",
            trait="Exaggerated pelvic sway while checking phone screen.",
            evidence_start=50.0,  # Far outside scene window [5.0 -> 20.0]
            evidence_end=55.0,
        )
        obs = SceneObservation(
            scene_id="scene_002",
            source_id="kardashian_inflate",
            window_start=5.0,
            window_end=20.0,
            characters=[CharacterObservation(character_id="christ_kardashia", kinematics=[bad_trait])],
        )
        report = self.validator.validate(obs, self.sample_scene)
        self.assertFalse(report.is_valid)
        self.assertEqual(report.error_count, 1)
        self.assertIn("TIMESTAMP_OUT_OF_BOUNDS", report.errors[0])

    def test_validator_passes_clean_mechanics(self):
        clean_trait = BehavioralTrait(
            category="kinematics",
            trait="Unbothered sideways glance while examining fingernails, completely detached from the physical procedure.",
            evidence_start=7.0,
            evidence_end=12.0,
            example_paraphrase="She inspects her manicure without acknowledging the danger.",
        )
        obs = SceneObservation(
            scene_id="scene_002",
            source_id="kardashian_inflate",
            window_start=5.0,
            window_end=20.0,
            characters=[CharacterObservation(character_id="christ_kardashia", kinematics=[clean_trait])],
        )
        report = self.validator.validate(obs, self.sample_scene)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.passed_traits_count, 1)

    def test_extractor_auto_repair_loop(self):
        # First response leaks quote; second response fixes it
        bad_json = json.dumps({
            "scene_id": "scene_002",
            "source_id": "kardashian_inflate",
            "window_start": 5.0,
            "window_end": 20.0,
            "characters": [{
                "character_id": "christ_kardashia",
                "kinematics": [],
                "idiolect": [],
                "status_moves": [],
                "rationalization_patterns": [{
                    "category": "rationalization",
                    "trait": "She says putting used jello shots and petroleum in her body is fine.",
                    "evidence_start": 6.0,
                    "evidence_end": 10.0,
                }]
            }]
        })

        good_json = json.dumps({
            "scene_id": "scene_002",
            "source_id": "kardashian_inflate",
            "window_start": 5.0,
            "window_end": 20.0,
            "characters": [{
                "character_id": "christ_kardashia",
                "kinematics": [],
                "idiolect": [],
                "status_moves": [],
                "rationalization_patterns": [{
                    "category": "rationalization",
                    "trait": "Treats extreme bodily hazard as routine aesthetic maintenance without fear.",
                    "evidence_start": 6.0,
                    "evidence_end": 10.0,
                }]
            }]
        })

        mock_llm = MagicMock(side_effect=[bad_json, good_json])
        extractor = BehavioralExtractor(llm_caller=mock_llm, validator=self.validator, max_repairs=2)

        result = extractor.extract_scene(self.sample_scene, source_id="kardashian_inflate")
        self.assertEqual(mock_llm.call_count, 2)
        self.assertEqual(result.characters[0].rationalization_patterns[0].trait, "Treats extreme bodily hazard as routine aesthetic maintenance without fear.")


if __name__ == "__main__":
    unittest.main()
