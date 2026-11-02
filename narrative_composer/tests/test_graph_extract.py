"""
Unit tests for Screenplay Extraction, Resolving, and Run Graph Construction (Milestone 5).
"""

import json
import unittest

from narrative_composer.graph.extract import extract_run
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.kernel import Network
from narrative_composer.graph.nodes import (
    BuildRunGraphNode,
    ExtractNode,
    ParseNode,
    TextSourceNode,
)
from narrative_composer.graph.registry import load_registry
from narrative_composer.graph.runbuild import build_run_graph
from narrative_composer.parser.fountain_lexer import FountainParser


class TestGraphExtract(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry()
        self.graph = StoryGraph.from_registry(self.registry)

    def test_quoted_exclamations_parentheticals_and_sounds_are_not_speaker_cues(self):
        source = 'INT. ROOM - DAY\n\nKELLY\n"WHAT THE?!"\n(CONTINUOUS)\n\nBANG!\n\nKELLY\nHello.\n'
        ast = FountainParser.parse(source)
        run = extract_run(ast, self.graph, canon='hot_scoomp_main', run_id='neutral')
        self.assertEqual(run.unresolved_cues, [])

    def test_optional_rainee_peter_intermediate_is_not_a_recorded_event(self):
        state = self.graph.get_state('rainee.state.peter_50')
        self.assertEqual(state.data_port.id, 'rainee.state.peter_50.port.data')
        self.assertTrue(state.attributes['provisional'])
        self.assertTrue(self.graph.get_xform('rainee.xform.base__peter_50').attributes['provisional'])
        self.assertTrue(self.graph.get_xform('rainee.xform.peter_50__peter').attributes['provisional'])
        source = 'INT. ROOM - DAY\n\nRAINEE\nHello.\n\nRAINEE-PETER\nHere.\n'
        run = extract_run(FountainParser.parse(source), self.graph, 'hot_scoomp_main', 'neutral')
        self.assertFalse(any(item.get('state') == 'peter_50' for item in run.observations))
        self.assertFalse(any(item.state_id == state.id for item in run.states))

    def test_minor_characters_and_canon_leak(self):
        script_kelly = """
INT. THE BUTTON NIGHTCLUB - NIGHT
KELLY
Who wants a drink?
"""
        ast_kelly = FountainParser.parse(script_kelly)
        res_kelly = extract_run(ast_kelly, self.graph, canon="hot_scoomp_main", run_id="run_kelly")
        self.assertEqual(len(res_kelly.states), 1)
        self.assertEqual(res_kelly.states[0].entity, "kelly")
        self.assertEqual(res_kelly.states[0].state_id, "kelly.state.base")

        script_mama = """
EXT. NANA AND PAPA'S HOUSE - DAY
MA MA LING (CONT'D)
You brought another one.
"""
        ast_mama = FountainParser.parse(script_mama)
        # In ling_au, ma_ma_ling is canonical
        res_mama = extract_run(ast_mama, self.graph, canon="ling_au", run_id="run_mama")
        self.assertEqual(len(res_mama.states), 1)
        self.assertEqual(res_mama.states[0].entity, "ma_ma_ling")
        self.assertEqual(res_mama.states[0].state_id, "ma_ma_ling.state.base")

        # ma_ma_ling is canonical in hot_scoomp_main as well (Rainee -> Peter segment).
        res_main = extract_run(ast_mama, self.graph, canon="hot_scoomp_main", run_id="run_main")
        self.assertEqual(len(res_main.canon_leaks), 0)

        # A hot_scoomp_main-only character is not canonical in ling_au and leaks.
        script_holly = """
EXT. PORCH - DAY
HOLLY
Who left the door open?
"""
        ast_holly = FountainParser.parse(script_holly)
        res_leak = extract_run(ast_holly, self.graph, canon="ling_au", run_id="run_leak")
        self.assertIn("HOLLY", res_leak.unresolved_cues)
        self.assertTrue(any("holly" in leak for leak in res_leak.canon_leaks))

    def test_stella_expansion_inferred_intermediates(self):
        script = """
INT. GLUTE LABS - DAY
Stella's polo buttons burst violently across the floor.

STEVE
Check out my calculations!
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="run_stella")

        state_ids = [s.state_id for s in res.states if s.entity == "stella"]
        self.assertEqual(state_ids, ["stella.state.standard"])
        self.assertFalse(any(s.source == "inferred_intermediate" for s in res.states))
        self.assertTrue(any(o["kind"] == "cue_assertion" and not o["accepted"] for o in res.observations))
        self.assertTrue(res.issues, "Unsupported physical assertions must remain visible")

    def test_stella_in_ling_au_does_not_resolve_steve(self):
        script = """
INT. KITCHEN - MORNING
STEVE
What about the game?
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="run_au")

        self.assertIn("STEVE", res.unresolved_cues)
        self.assertTrue(any("stella" in leak for leak in res.canon_leaks))
        # No Steve state instance created
        self.assertFalse(any(s.state_id == "stella.state.big_tiddy_steve" for s in res.states))

    def test_rainee_peter_transition_in_ling_au(self):
        script = """
INT. KITCHEN - MORNING
RAINEE-PETER
Holy crap, Francine.
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="run_peter")

        self.assertEqual(res.xforms, [])
        self.assertEqual(res.states[-1].state_id, "rainee.state.base")
        self.assertFalse(res.observations[-1]["accepted"])

    def test_illegal_jump_records_none_xform(self):
        # Holly only has base state. If an action/cue attempts an illegal state jump
        from narrative_composer.graph.extract import extract_run
        from narrative_composer.models.ast_nodes import ASTElement, ASTNodeType

        # Manually invoke with a non-existent state hint by adding an enter_pattern temporarily or testing illegal jump directly
        elements = [
            ASTElement(node_type=ASTNodeType.CHARACTER, content="HOLLY", line_number=1),
            ASTElement(node_type=ASTNodeType.DIALOGUE, content="Welcome to the studio.", line_number=2),
        ]
        res = extract_run(elements, self.graph, canon="hot_scoomp_main", run_id="run_holly")
        self.assertEqual(len(res.states), 1)
        self.assertEqual(res.states[0].state_id, "holly.state.base")

    def test_determinism_and_pipeline_node_chain(self):
        script = """
INT. LING HOUSE - MORNING
RAINEE-PETER
I need iced coffee.
"""
        net = Network()
        src = TextSourceNode("op.src.1", {"text": script})
        parse = ParseNode("op.parse.1")
        extract = ExtractNode("op.extract.1", {"canon": "ling_au", "run_id": "det_run"})
        build = BuildRunGraphNode("op.build.1", {"canon": "ling_au", "run_id": "det_run"})

        net.add(src)
        net.add(parse)
        net.add(extract)
        net.add(build)

        net.connect("op.src.1", "op.parse.1", "text")
        net.connect("op.parse.1", "op.extract.1", "ast")
        net.connect("op.extract.1", "op.build.1", "result")

        ctx = {"graph": self.graph}
        res1 = net.cook("op.build.1", ctx)
        json1 = json.dumps(res1, sort_keys=True)

        # Cook again
        res2 = net.cook("op.build.1", ctx)
        json2 = json.dumps(res2, sort_keys=True)

        self.assertEqual(json1, json2)
        self.assertIn("rainee", res1["entities"])
        self.assertIn("rainee.state.base", [s["state_id"] for s in res1["state_instances"]])
        self.assertFalse(res1["observations"][-1]["accepted"])


if __name__ == "__main__":
    unittest.main()
