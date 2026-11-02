"""
Unit tests for Autonomous Character and State Discovery (Milestone 5.5).
"""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.graph.discover import (
    apply_discovery,
    discover,
    persist_discovery,
)
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import EntityDef, StateDef
from narrative_composer.graph.registry import load_registry
from narrative_composer.parser.fountain_lexer import FountainParser


class TestGraphDiscover(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry(include_auto=False)
        self.graph = StoryGraph.from_registry(self.registry)

    def test_1_new_cue_becomes_entity(self):
        script = """
INT. COFFEE SHOP - DAY
ZARA
Hello world.

ZARA
I need another latte.
"""
        ast = FountainParser.parse(script)
        res = discover(ast, self.graph, canon="hot_scoomp_main", run_id="run_zara")

        eids = [e["entity_id"] for e in res.new_entities]
        self.assertIn("zara", eids)
        zara_ent = next(e for e in res.new_entities if e["entity_id"] == "zara")
        self.assertEqual(zara_ent["attributes"]["confidence"], 0.9)
        self.assertEqual(zara_ent["canons"], ["hot_scoomp_main"])
        self.assertEqual(zara_ent["states"][0]["id"], "zara.state.base")

    def test_2_all_caps_action_with_mixed_case_mention(self):
        # STAN SMITH stands by his mailbox. Stan drops the rake.
        script = """
EXT. DRIVEWAY - DAY
STAN SMITH stands by his mailbox in creased denim jeans.
Stan drops the rake.
"""
        ast = FountainParser.parse(script)
        res = discover(ast, self.graph, canon="ling_au", run_id="run_stan")
        eids = [e["entity_id"] for e in res.new_entities]
        self.assertIn("stan_smith", eids)

        # Isolated ALL-CAPS without mixed-case occurrence does NOT create an entity
        isolated_script = """
EXT. DRIVEWAY - DAY
SOME RANDOM GUY stands in the cold.
The wind blows.
"""
        ast_iso = FountainParser.parse(isolated_script)
        res_iso = discover(ast_iso, self.graph, canon="ling_au", run_id="run_iso")
        self.assertNotIn("some_random_guy", [e["entity_id"] for e in res_iso.new_entities])

    def test_3_sound_and_heading_words_filtered(self):
        script = """
INT. KITCHEN - MORNING
CRACK! BRAAAP!
GPS VOICE
Turn right.
"""
        ast = FountainParser.parse(script)
        res = discover(ast, self.graph, canon="ling_au", run_id="run_noise")
        eids = [e["entity_id"] for e in res.new_entities]
        self.assertNotIn("crack", eids)
        self.assertNotIn("braaap", eids)
        self.assertNotIn("gps_voice", eids)

    def test_4_name_normalization_deduplication(self):
        script = """
EXT. PORCH - DAY
BAH-BAH sits in the recliner.
Later, Bah Bah shifts slightly.
"""
        ast = FountainParser.parse(script)
        res = discover(ast, self.graph, canon="ling_au", run_id="run_bah")
        # BAH-BAH and Bah Bah normalize to same key BAHBAH
        eids = [e["entity_id"] for e in res.new_entities]
        self.assertIn("bah_bah", eids)
        # Exactly one entity created
        self.assertEqual(len([e for e in res.new_entities if "bah" in e["entity_id"]]), 1)

    def test_5_rainee_peter_state_discovery(self):
        # Create a graph where rainee exists but does not yet have 'peter' state
        fresh_rainee = EntityDef(
            entity_id="rainee_test",
            display_name="Rainee Test",
            base_state="base",
            states=[StateDef(id="rainee_test.state.base", slug="base", label="Base")],
        )
        test_graph = StoryGraph(entities={"rainee_test": fresh_rainee})

        script = """
INT. KITCHEN - MORNING
RAINEE_TEST-PETER
Holy crap!
"""
        ast = FountainParser.parse(script)
        res = discover(ast, test_graph, canon="ling_au", run_id="run_p")
        self.assertEqual(len(res.new_states), 1)
        st = res.new_states[0]["state"]
        self.assertEqual(st["id"], "rainee_test.state.peter")
        self.assertEqual(st["attributes"]["origin"], "auto")

        self.assertEqual(len(res.new_xforms), 1)
        xf = res.new_xforms[0]["xform"]
        self.assertEqual(xf["id"], "rainee_test.xform.base__peter")

    def test_6_action_transformation_sentence(self):
        script = """
INT. KITCHEN - MORNING
Rainee transforms into a bloated Peter.
"""
        ast = FountainParser.parse(script)
        # Note: Rainee already has peter state in standard seed, so test with a novel phrase or fresh entity
        fresh_rainee = EntityDef(
            entity_id="rainee",
            display_name="Rainee",
            base_state="base",
            states=[StateDef(id="rainee.state.base", slug="base", label="Base")],
        )
        test_graph = StoryGraph(entities={"rainee": fresh_rainee})
        res = discover(ast, test_graph, canon="ling_au", run_id="run_morph")

        st_slugs = [s["state"]["slug"] for s in res.new_states]
        self.assertIn("bloated_peter", st_slugs)
        bloated_st = next(s["state"] for s in res.new_states if s["state"]["slug"] == "bloated_peter")
        self.assertEqual(bloated_st["attributes"]["confidence"], 0.6)

    def test_7_relation_words_become_new_entities(self):
        script = """
INT. ENTRY - DAY
FRANCINE'S MOM
Do not sit on the good couch!
"""
        ast = FountainParser.parse(script)
        res = discover(ast, self.graph, canon="ling_au", run_id="run_mom")
        # Should NOT become a state of Francine; must become a new entity
        self.assertFalse(any(s["entity"] == "francine" for s in res.new_states))
        new_eids = [e["entity_id"] for e in res.new_entities]
        self.assertTrue(any("mom" in eid for eid in new_eids))

    def test_8_idempotence(self):
        script = """
INT. BASEMENT - NIGHT
NEWTON
I discovered gravity.

NEWTON
And apples.
"""
        ast = FountainParser.parse(script)
        res1 = discover(ast, self.graph, canon="hot_scoomp_main", run_id="run_idem")
        self.assertEqual(len(res1.new_entities), 1)

        # Apply discovery to graph
        updated_graph = apply_discovery(self.graph, res1)
        # Run discovery again on same text with updated graph
        res2 = discover(ast, updated_graph, canon="hot_scoomp_main", run_id="run_idem2")
        self.assertEqual(len(res2.new_entities), 0)
        self.assertEqual(len(res2.new_states), 0)

    def test_9_collision_suffixing(self):
        # Entity with existing id "zara_smith" exists with distinct alias
        zara_ent = EntityDef(
            entity_id="zara_smith",
            display_name="Zara Smith-Jones",
            aliases=["ZARA SMITH JONES"],
            base_state="base",
            states=[StateDef(id="zara_smith.state.base", slug="base", label="Base")],
        )
        test_graph = StoryGraph(entities={"zara_smith": zara_ent})

        # Discover a different speaker "ZARA SMITH" whose slug matches "zara_smith"
        script = """
INT. ROOM - DAY
ZARA SMITH
I am different.
"""
        ast = FountainParser.parse(script)
        res = discover(ast, test_graph, canon="hot_scoomp_main", run_id="run_col")
        self.assertEqual(len(res.new_entities), 1)
        self.assertEqual(res.new_entities[0]["entity_id"], "zara_smith_2")

    def test_10_no_learn_memory_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            script = """
INT. YARD - DAY
FREDDY
Hello there!
"""
            ast = FountainParser.parse(script)
            res = discover(ast, self.graph, canon="ling_au", run_id="run_nl")
            # Apply in memory only
            updated = apply_discovery(self.graph, res)
            self.assertIn("freddy", updated.entities)
            # Ensure no files written to tmpdir
            self.assertEqual(list(tmp_path.glob("*.json")), [])

    def test_11_max_entities_cap(self):
        # Create text with 35 unique speakers
        cues = [f"CHAR_{i:02d}\nI am number {i}." for i in range(35)]
        script = "INT. AUDITORIUM - DAY\n" + "\n\n".join(cues)
        ast = FountainParser.parse(script)

        cfg = {"max_new_entities_per_run": 10, "ignore_cues": []}
        res = discover(ast, self.graph, canon="hot_scoomp_main", run_id="run_cap", cfg=cfg)
        self.assertEqual(len(res.new_entities), 10)

    def test_12_determinism(self):
        script = """
INT. GYM - DAY
COACH CARTER
Run faster!
Stan drops the ball.
"""
        ast = FountainParser.parse(script)
        res1 = discover(ast, self.graph, canon="hot_scoomp_main", run_id="run_d")
        res2 = discover(ast, self.graph, canon="hot_scoomp_main", run_id="run_d")

        ops1 = json.dumps(res1.patch_ops, sort_keys=True)
        ops2 = json.dumps(res2.patch_ops, sort_keys=True)
        self.assertEqual(ops1, ops2)


if __name__ == "__main__":
    unittest.main()
