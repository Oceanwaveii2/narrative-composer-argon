"""
Unit tests for Milestone 3: Dialectic Character Node models, trait aggregation,
provenance preservation, and prompt directive synthesis.
"""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.ingest.aggregate import TraitAggregator
from narrative_composer.models.character import (
    DialecticCharacterNode,
    DialecticPole,
    DialecticTrait,
    Provenance,
    SynthesisRule,
)


class TestCharacterModelsAndAggregation(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dialectic_character_node_roundtrip(self):
        prov = Provenance(
            source_id="hot_scoomp_s18e11",
            scene_id="scene_001",
            evidence_start=2.3,
            evidence_end=5.6,
        )
        trait = DialecticTrait(
            trait_id="trait_001",
            category="kinematics",
            description="Upright posturing while gesturing with hand.",
            provenance=[prov],
            recurrence_count=2,
            confidence_score=0.9,
        )
        thesis = DialecticPole(
            pole_name="Thesis: Activist",
            core_drive="Social justice superiority",
            vocabulary_domain=["fair-trade", "organic"],
            traits=[trait],
        )
        antithesis = DialecticPole(
            pole_name="Antithesis: Influencer",
            core_drive="Luxury vanity",
            vocabulary_domain=["peach", "pop-and-lock"],
            traits=[],
        )
        rule = SynthesisRule(
            rule_id="rule_01",
            trigger="When questioned",
            mechanism="Uses organic rhetoric to defend vanity",
            example_volley="This peach is sustainable!",
        )

        node = DialecticCharacterNode(
            character_id="hayley",
            display_name="Hayley Smith",
            thesis=thesis,
            antithesis=antithesis,
            synthesis_rules=[rule],
            kinematics=[trait],
            idiolect=[],
            status_moves=[],
        )

        # Serialize & Deserialize
        json_str = node.model_dump_json()
        data = json.loads(json_str)
        reloaded = DialecticCharacterNode.model_validate(data)

        self.assertEqual(reloaded.character_id, "hayley")
        self.assertEqual(len(reloaded.thesis.vocabulary_domain), 2)
        self.assertEqual(reloaded.synthesis_rules[0].rule_id, "rule_01")
        self.assertEqual(reloaded.kinematics[0].provenance[0].source_id, "hot_scoomp_s18e11")

    def test_to_prompt_directive(self):
        trait_k = DialecticTrait(
            trait_id="t1",
            category="kinematics",
            description="Forward pelvic tilt with dismissive hand wave",
            provenance=[],
        )
        trait_i = DialecticTrait(
            trait_id="t2",
            category="idiolect",
            description="Vocal fry on vowel endings with rising pitch",
            provenance=[],
        )
        trait_s = DialecticTrait(
            trait_id="t3",
            category="status_move",
            description="Condescending compliments that double as put-downs",
            provenance=[],
        )
        thesis = DialecticPole(
            pole_name="Thesis",
            core_drive="Anti-capitalist purity",
            vocabulary_domain=["bamboo", "fair-trade"],
            traits=[],
        )
        antithesis = DialecticPole(
            pole_name="Antithesis",
            core_drive="Billion-dollar vanity",
            vocabulary_domain=["luxury asset", "pop-and-lock"],
            traits=[],
        )
        rule = SynthesisRule(
            rule_id="r1",
            trigger="Challenge",
            mechanism="Rationalizes luxury vanity through eco-righteous framing",
            example_volley="My peach is fair trade!",
        )

        node = DialecticCharacterNode(
            character_id="hayley",
            display_name="Hayley Smith",
            thesis=thesis,
            antithesis=antithesis,
            synthesis_rules=[rule],
            kinematics=[trait_k],
            idiolect=[trait_i],
            status_moves=[trait_s],
        )

        directive = node.to_prompt_directive(token_budget=120)
        self.assertIn("HAYLEY SMITH BEHAVIORAL ENGINE", directive)
        self.assertIn("Anti-capitalist purity", directive)
        self.assertIn("Billion-dollar vanity", directive)
        self.assertIn("bamboo", directive)
        self.assertIn("luxury asset", directive)
        self.assertIn("Forward pelvic tilt", directive)
        self.assertIn("Vocal fry on vowel endings", directive)
        self.assertIn("Condescending compliments", directive)
        self.assertIn("COMEDIC SYNTHESIS:", directive)

    def test_trait_aggregator_end_to_end(self):
        # Create a mock observations file
        obs_file = self.work_dir / "sample_obs.json"
        sample_obs_data = {
            "source_id": "hot_scoomp_s18e11",
            "observations": [
                {
                    "scene_id": "scene_001",
                    "source_id": "hot_scoomp_s18e11",
                    "window_start": 0.0,
                    "window_end": 15.0,
                    "characters": [
                        {
                            "character_id": "hayley",
                            "kinematics": [
                                {
                                    "category": "kinematics",
                                    "trait": "Dynamic hand gestures asserting confidence",
                                    "evidence_start": 2.0,
                                    "evidence_end": 6.0,
                                }
                            ],
                            "idiolect": [
                                {
                                    "category": "idiolect",
                                    "trait": "Vocal fry on vowels conveying laid-back tone",
                                    "evidence_start": 3.0,
                                    "evidence_end": 7.0,
                                }
                            ],
                            "status_moves": [
                                {
                                    "category": "status_move",
                                    "trait": "Smug self-congratulation before achieving results",
                                    "evidence_start": 1.0,
                                    "evidence_end": 4.0,
                                }
                            ],
                            "rationalization_patterns": [
                                {
                                    "category": "rationalization",
                                    "trait": "Frames personal crusade as morally essential",
                                    "evidence_start": 5.0,
                                    "evidence_end": 10.0,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with open(obs_file, "w", encoding="utf-8") as fh:
            json.dump(sample_obs_data, fh)

        out_json = self.work_dir / "hayley.json"
        out_review = self.work_dir / "review.md"

        node = TraitAggregator.compile_hayley_node(
            observation_file_paths=[str(obs_file)],
            output_json_path=str(out_json),
            output_review_md=str(out_review),
        )

        self.assertEqual(node.character_id, "hayley")
        self.assertTrue(out_json.exists())
        self.assertTrue(out_review.exists())

        review_content = out_review.read_text(encoding="utf-8")
        self.assertIn("Character Node Audit & Provenance Review", review_content)
        self.assertIn("Dynamic hand gestures asserting confidence", review_content)
        self.assertIn("hot_scoomp_s18e11", review_content)


if __name__ == "__main__":
    unittest.main()
