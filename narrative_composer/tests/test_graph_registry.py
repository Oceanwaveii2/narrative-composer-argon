"""
Unit tests for Narrative Node Graph Registry Loader and Seed Data (Milestone 2).
"""

import tempfile
import unittest
from pathlib import Path

from narrative_composer.graph.registry import load_entity, load_registry


class TestGraphRegistry(unittest.TestCase):

    def test_load_all_seed_entities(self):
        registry = load_registry(include_auto=False)
        expected_entities = [
            "francine",
            "haley",
            "holly",
            "kelly",
            "ma_ma_ling",
            "rainee",
            "stella",
        ]
        self.assertEqual(sorted(list(registry.keys())), expected_entities)
        self.assertEqual(len(registry), 7)

        # Stella state and transform invariants
        stella = registry["stella"]
        self.assertTrue({'standard','nerd_20','nerd_40','nerd_70','nerd_80','big_tiddy_steve','poser_nerd'}
                        <= {state.slug for state in stella.states})
        self.assertEqual(len(stella.transforms), 3)

        # Minor character invariants
        kelly = registry["kelly"]
        self.assertEqual(len(kelly.states), 1)
        self.assertEqual(len(kelly.transforms), 0)

        ma_ma_ling = registry["ma_ma_ling"]
        self.assertEqual(len(ma_ma_ling.states), 1)
        self.assertEqual(len(ma_ma_ling.transforms), 0)

    def test_transform_referential_integrity(self):
        registry = load_registry()
        for entity_id, entity in registry.items():
            state_id_set = {s.id for s in entity.states}
            for xf in entity.transforms:
                self.assertIn(
                    xf.from_state,
                    state_id_set,
                    f"Transform {xf.id} in entity {entity_id} references nonexistent from_state {xf.from_state}",
                )
                self.assertIn(
                    xf.to_state,
                    state_id_set,
                    f"Transform {xf.id} in entity {entity_id} references nonexistent to_state {xf.to_state}",
                )

    def test_duplicate_entity_id_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create two files with the same entity_id
            f1 = tmp_path / "char1.json"
            f2 = tmp_path / "char2.json"
            content = """{
                "schema_version": 1,
                "entity_id": "duplicate_char",
                "display_name": "Duplicate Character",
                "base_state": "base",
                "states": [{"id": "duplicate_char.state.base", "slug": "base", "label": "Base"}]
            }"""
            f1.write_text(content, encoding="utf-8")
            f2.write_text(content, encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                load_registry(tmp_path)
            self.assertIn("Duplicate entity_id 'duplicate_char'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
