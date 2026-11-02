"""
Unit tests for Narrative Node Graph IDs and Models (Milestone 1).
"""

import unittest
from narrative_composer.graph.ids import (
    is_valid_id,
    slugify,
    state_id,
    xform_id,
    parse_id,
)
from narrative_composer.graph.models import (
    CueAlias,
    StateDef,
    TransformDef,
    EntityDef,
    Annotation,
    StoryTime,
    StateInstance,
    TransformInstance,
    Violation,
    Suggestion,
    SCHEMA_VERSION,
)


class TestGraphIDsAndModels(unittest.TestCase):

    def test_id_validation(self):
        # Valid IDs
        self.assertTrue(is_valid_id("stella"))
        self.assertTrue(is_valid_id("stella.state.nerd_20"))
        self.assertTrue(is_valid_id("stella.xform.nerd_20__nerd_80"))
        self.assertTrue(is_valid_id("ann.stella.state.nerd_20.1"))
        self.assertTrue(is_valid_id("run.ep16.rainee.inst.2"))
        self.assertTrue(is_valid_id("op.parse.1"))

        # Invalid IDs
        self.assertFalse(is_valid_id(""))
        self.assertFalse(is_valid_id("Stella"))  # Uppercase forbidden in canonical ID
        self.assertFalse(is_valid_id("stella..state"))
        self.assertFalse(is_valid_id("stella.state."))
        self.assertFalse(is_valid_id(".stella"))
        self.assertFalse(is_valid_id("stella state"))
        self.assertFalse(is_valid_id("stella-state"))  # Dash forbidden; underscore required

    def test_slugify(self):
        self.assertEqual(slugify("Big Tiddy Steve"), "big_tiddy_steve")
        self.assertEqual(slugify("Stella-Nerd 20%"), "stella_nerd_20")
        self.assertEqual(slugify("  ___Hello__World___ "), "hello_world")

    def test_id_constructors(self):
        self.assertEqual(state_id("stella", "nerd_20"), "stella.state.nerd_20")
        self.assertEqual(
            xform_id("stella", "nerd_20", "nerd_80"),
            "stella.xform.nerd_20__nerd_80"
        )

    def test_parse_id(self):
        res = parse_id("stella.state.nerd_20")
        self.assertEqual(res["entity"], "stella")
        self.assertEqual(res["kind"], "state")
        self.assertEqual(res["slug"], "nerd_20")

        res_xf = parse_id("stella.xform.nerd_20__nerd_80")
        self.assertEqual(res_xf["entity"], "stella")
        self.assertEqual(res_xf["kind"], "xform")
        self.assertEqual(res_xf["from_slug"], "nerd_20")
        self.assertEqual(res_xf["to_slug"], "nerd_80")

        with self.assertRaises(ValueError):
            parse_id("invalid..id")

    def test_state_def_validation(self):
        # Valid StateDef
        s = StateDef(
            id="stella.state.nerd_20",
            slug="nerd_20",
            label="Dork 20%",
            order=1,
        )
        self.assertEqual(s.slug, "nerd_20")

        # Mismatched ID raises ValueError
        with self.assertRaises(ValueError):
            StateDef(
                id="stella.state.mismatched_slug",
                slug="nerd_20",
                label="Dork 20%",
            )

        # Non-state kind raises ValueError
        with self.assertRaises(ValueError):
            StateDef(
                id="stella.xform.nerd_20",
                slug="nerd_20",
                label="Dork 20%",
            )

    def test_transform_def_validation(self):
        # Valid TransformDef
        t = TransformDef(
            id="stella.xform.nerd_20__nerd_80",
            from_state="stella.state.nerd_20",
            to_state="stella.state.nerd_80",
            triggers=["pink_cube"],
        )
        self.assertEqual(t.triggers, ["pink_cube"])

        # Mismatched transform ID raises ValueError
        with self.assertRaises(ValueError):
            TransformDef(
                id="stella.xform.wrong__id",
                from_state="stella.state.nerd_20",
                to_state="stella.state.nerd_80",
            )

        # Cross-entity transform raises ValueError
        with self.assertRaises(ValueError):
            TransformDef(
                id="stella.xform.nerd_20__peter",
                from_state="stella.state.nerd_20",
                to_state="rainee.state.peter",
            )

    def test_entity_def_and_roundtrip(self):
        s1 = StateDef(id="stella.state.standard", slug="standard", label="Standard Stella", order=0)
        s2 = StateDef(id="stella.state.nerd_20", slug="nerd_20", label="Dork 20%", order=1)
        xf = TransformDef(
            id="stella.xform.standard__nerd_20",
            from_state="stella.state.standard",
            to_state="stella.state.nerd_20",
            triggers=["pink_cube"],
        )

        entity = EntityDef(
            schema_version=SCHEMA_VERSION,
            entity_id="stella",
            display_name="Stella",
            aliases=["STELLA"],
            canons=["hot_scoomp_main"],
            base_state="standard",
            states=[s1, s2],
            transforms=[xf],
        )

        # Round-trip serialization
        json_data = entity.model_dump_json()
        restored = EntityDef.model_validate_json(json_data)
        self.assertEqual(entity, restored)

        # Invalid base state raises ValueError
        with self.assertRaises(ValueError):
            EntityDef(
                entity_id="stella",
                display_name="Stella",
                base_state="nonexistent_base",
                states=[s1, s2],
            )


if __name__ == "__main__":
    unittest.main()
