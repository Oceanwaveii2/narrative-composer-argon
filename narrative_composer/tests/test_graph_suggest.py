"""
Unit tests for Context-Specific Suggestion Engine (Milestone 8).
"""

import unittest

from narrative_composer.graph.enrich import attach
from narrative_composer.graph.extract import extract_run
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import Annotation
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.suggest import suggest
from narrative_composer.graph.world_port import PrototypeWorld
from narrative_composer.parser.fountain_lexer import FountainParser


class TestGraphSuggest(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)
        self.world = PrototypeWorld()

    def test_reaction_beat_suggestion(self):
        # Rainee transforms to Peter, but no other character reacts in the next 8 lines
        script = """
INT. KITCHEN - MORNING
> EVENT: peter_protocol
Rainee follows the peter protocol.

RAINEE-PETER
Holy crap!

The kitchen clock ticks loudly.
The refrigerator hums on its low cycle.
Rainee looks at the kitchen island.
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="run_rb")
        suggs = suggest(res, self.graph, canon="ling_au", elements=ast)

        rb = [s for s in suggs if s.kind == "reaction_beat"]
        self.assertEqual(len(rb), 1)
        self.assertIn("Rainee changes to", rb[0].text)
        self.assertIn("no reaction from another character", rb[0].text)
        self.assertIn("rainee.state.peter", rb[0].context_node_ids)

    def test_callback_available_suggestion(self):
        # Attach a lore annotation with specific tags targeting nurse_deluxe
        ann = Annotation(
            id="ann.francine.state.nurse_deluxe.1",
            target_id="francine.state.nurse_deluxe",
            source="test_lore",
            kind="lore",
            text="Francine once stole an ambulance during nursing residency.",
            tags=["ambulance", "residency"],
            canons=["ling_au"],
        )
        attach(self.graph, ann)

        script = """
INT. ENTRY - DAY
> EVENT: uniform_change
Francine changes into a nurse uniform.

NURSE FRANCINE DELUXE
I'm ready for the rounds!
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="run_cb")
        suggs = suggest(res, self.graph, canon="ling_au", elements=ast)

        cb = [s for s in suggs if s.kind == "callback"]
        self.assertEqual(len(cb), 1)
        self.assertIn("stole an ambulance", cb[0].text)
        self.assertIn("ann.francine.state.nurse_deluxe.1", cb[0].context_node_ids)

    def test_relationship_echo_suggestion(self):
        # In hot_scoomp_main, Holly and Haley are in girlfriend relationship.
        # Script puts Haley in room, Holly is mentioned in action, but no direct dialogue.
        script = """
INT. HG STUDIO - DAY
HALEY
I'm here for my session.

Holly Graham observes from the office doorway, arms folded.
The music pounds on the sound system.
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="run_rel")
        suggs = suggest(res, self.graph, canon="hot_scoomp_main", elements=ast, world=self.world)

        rel_suggs = [s for s in suggs if s.kind == "relationship_echo"]
        self.assertTrue(len(rel_suggs) >= 1)
        self.assertIn("girlfriend partner", rel_suggs[0].text)
        self.assertIn("holly", rel_suggs[0].text)

    def test_skipped_stage_suggestion(self):
        # Stella transitions from standard directly to STEVE (triggering intermediate nerd_20 and nerd_80)
        script = """
INT. GLUTE LABS - DAY
STEVE
Calculations complete!
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="run_skip")
        suggs = suggest(res, self.graph, canon="hot_scoomp_main", elements=ast)

        skip_suggs = [s for s in suggs if s.kind == "skipped_stage"]
        # Both nerd_20 and nerd_80 should be recommended for showcase
        self.assertEqual(skip_suggs, [], "Do not manufacture intermediate history from a cue")
        self.assertTrue(any(not o["accepted"] for o in res.observations))

    def test_deterministic_sorting(self):
        script = """
INT. KITCHEN - MORNING
> EVENT: peter_protocol
Rainee follows the peter protocol.

RAINEE-PETER
Hello!
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="run_det")
        suggs1 = suggest(res, self.graph, canon="ling_au", elements=ast)
        suggs2 = suggest(res, self.graph, canon="ling_au", elements=ast)

        t1 = [(s.line, s.entity, s.kind, s.text) for s in suggs1]
        t2 = [(s.line, s.entity, s.kind, s.text) for s in suggs2]
        self.assertEqual(t1, t2)


if __name__ == "__main__":
    unittest.main()
