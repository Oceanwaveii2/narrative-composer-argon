"""
Unit tests for Graph-Driven Integrity, Continuity, and Canon Checks (Milestone 7).
"""

import unittest

from narrative_composer.graph.checks import run_checks
from narrative_composer.graph.extract import extract_run
from narrative_composer.graph.graph import StoryGraph
from narrative_composer.graph.models import EntityDef, StateDef, TransformDef
from narrative_composer.graph.registry import load_registry
from narrative_composer.parser.fountain_lexer import FountainParser


class TestGraphChecks(unittest.TestCase):

    def setUp(self):
        self.registry = load_registry(include_auto=False)
        self.graph = StoryGraph.from_registry(self.registry)

    def test_clean_script_zero_errors(self):
        script = """
INT. THE BUTTON NIGHTCLUB - NIGHT
KELLY
Who wants a round of drinks?
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="clean_run")
        violations = run_checks(res, self.graph, canon="hot_scoomp_main", elements=ast)
        errors = [v for v in violations if v.severity == "ERROR"]
        self.assertEqual(len(errors), 0)

    def test_g1_illegal_transition(self):
        # Holly has no transitions defined from base state.
        # If an action attempts an unsupported jump, xform_id is None -> G1_ILLEGAL_TRANSITION
        from narrative_composer.graph.extract import RunResult
        from narrative_composer.graph.models import StoryTime, TransformInstance

        fake_res = RunResult()
        fake_res.xforms.append(
            TransformInstance(
                id="run.test.holly.xform.1",
                entity="holly",
                xform_id=None,  # illegal jump
                from_state="holly.state.base",
                to_state="holly.state.unknown_stage",
                at=StoryTime(scene_index=0, line=10),
                source="explicit",
            )
        )
        violations = run_checks(fake_res, self.graph, canon="hot_scoomp_main", elements=[])
        g1 = [v for v in violations if v.rule_id == "G1_ILLEGAL_TRANSITION"]
        self.assertEqual(len(g1), 1)
        self.assertEqual(g1[0].severity, "ERROR")
        self.assertIn("Illegal state transition", g1[0].message)

    def test_g2_cue_state_mismatch(self):
        # Script uses STEVE cue without the physical polo burst trigger having occurred
        # Stella is in standard state, but cue STEVE implies big_tiddy_steve
        script = """
INT. GLUTE LABS - DAY
STEVE
Look at this math equation!
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="mismatch_run")
        # In extract_run, STEVE immediately causes path transition standard -> nerd_20 -> nerd_80 -> big_tiddy_steve
        # So at line 3, big_tiddy_steve was reached.
        # To test G2 specifically: if cue implies a state that does not match history
        # Let's inspect violations
        violations = run_checks(res, self.graph, canon="hot_scoomp_main", elements=ast)
        # If STEVE triggered transition at line 3, then history has line 3 = big_tiddy_steve
        # If we have a cue where the entity was forced into standard state:
        from narrative_composer.graph.extract import RunResult
        from narrative_composer.graph.models import StateInstance, StoryTime
        manual_res = RunResult()
        manual_res.states.append(
            StateInstance(
                id="inst.1",
                entity="stella",
                state_id="stella.state.standard",
                at=StoryTime(scene_index=0, line=1),
                source="base",
            )
        )
        violations = run_checks(manual_res, self.graph, canon="hot_scoomp_main", elements=ast)
        g2 = [v for v in violations if v.rule_id == "G2_CUE_STATE_MISMATCH"]
        self.assertEqual(len(g2), 1)
        self.assertEqual(g2[0].severity, "ERROR")

    def test_g3_canon_leak(self):
        script = """
INT. LIVING ROOM - DAY
HOLLY
Watch out for the couch!
"""
        ast = FountainParser.parse(script)
        # HOLLY is scoped to hot_scoomp_main, so she leaks in a ling_au run.
        res = extract_run(ast, self.graph, canon="ling_au", run_id="leak_run")
        violations = run_checks(res, self.graph, canon="ling_au", elements=ast)
        g3 = [v for v in violations if v.rule_id == "G3_CANON_LEAK"]
        self.assertTrue(len(g3) >= 1)
        self.assertEqual(g3[0].severity, "ERROR")
        self.assertIn("Canon boundary violation", g3[0].message)

    def test_g4_unexplained_revert(self):
        # Entity has A -> B (non-reversible). Reverting B -> A flags G4_UNEXPLAINED_REVERT
        test_ent = EntityDef(
            entity_id="dummy",
            display_name="Dummy",
            base_state="state_a",
            states=[
                StateDef(id="dummy.state.state_a", slug="state_a", label="A"),
                StateDef(id="dummy.state.state_b", slug="state_b", label="B"),
            ],
            transforms=[
                TransformDef(
                    id="dummy.xform.state_a__state_b",
                    from_state="dummy.state.state_a",
                    to_state="dummy.state.state_b",
                    reversible=False,
                )
            ],
        )
        test_graph = StoryGraph(entities={"dummy": test_ent})

        from narrative_composer.graph.extract import RunResult
        from narrative_composer.graph.models import StateInstance, StoryTime, TransformInstance

        res = RunResult()
        res.states.append(
            StateInstance(id="inst.1", entity="dummy", state_id="dummy.state.state_a", at=StoryTime(scene_index=0, line=1), source="base")
        )
        res.states.append(
            StateInstance(id="inst.2", entity="dummy", state_id="dummy.state.state_b", at=StoryTime(scene_index=0, line=5), source="explicit")
        )
        # Non-reversible return to state_a
        res.xforms.append(
            TransformInstance(
                id="xf.1",
                entity="dummy",
                xform_id="dummy.xform.state_a__state_b",
                from_state="dummy.state.state_b",
                to_state="dummy.state.state_a",
                at=StoryTime(scene_index=0, line=10),
                source="explicit",
            )
        )
        violations = run_checks(res, test_graph, canon="hot_scoomp_main", elements=[])
        g4 = [v for v in violations if v.rule_id == "G4_UNEXPLAINED_REVERT"]
        self.assertEqual(len(g4), 1)
        self.assertEqual(g4[0].severity, "WARNING")

    def test_g5_anchor_missing(self):
        # Rainee transitions to Peter, but no visual anchors (cleft chin, baritone, etc.) appear in next lines
        script = """
INT. KITCHEN - MORNING
> EVENT: peter_protocol
Rainee follows the peter protocol.

RAINEE-PETER
Hello.

She turns and looks around the room silently.
The tea kettle boils on the stove.
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="ling_au", run_id="peter_no_anchor")
        violations = run_checks(res, self.graph, canon="ling_au", elements=ast)
        g5 = [v for v in violations if v.rule_id == "G5_ANCHOR_MISSING"]
        self.assertEqual(len(g5), 1)
        self.assertEqual(g5[0].severity, "INFO")
        self.assertIn("visual anchors", g5[0].message)

    def test_g6_unresolved_cue(self):
        script = """
INT. ALLEY - NIGHT
MYSTERIOUS STRANGER
Who goes there?
"""
        ast = FountainParser.parse(script)
        res = extract_run(ast, self.graph, canon="hot_scoomp_main", run_id="unresolved_run")
        violations = run_checks(res, self.graph, canon="hot_scoomp_main", elements=ast)
        g6 = [v for v in violations if v.rule_id == "G6_UNRESOLVED_CUE"]
        self.assertEqual(len(g6), 1)
        self.assertEqual(g6[0].severity, "INFO")
        self.assertIn("MYSTERIOUS STRANGER", g6[0].message)

    def test_g7_auto_discovered_reporting(self):
        from narrative_composer.graph.extract import RunResult
        from narrative_composer.graph.models import StateInstance, StoryTime

        # Create provisional entity in graph
        prov_ent = EntityDef(
            entity_id="prov_char",
            display_name="Provisional Character",
            base_state="base",
            states=[
                StateDef(
                    id="prov_char.state.base",
                    slug="base",
                    label="Base",
                    attributes={"origin": "auto", "provisional": True, "confidence": 0.85, "evidence": "Cue 'PROV_CHAR'"},
                )
            ],
            attributes={"origin": "auto", "provisional": True, "confidence": 0.85, "evidence": "Cue 'PROV_CHAR'"},
        )
        test_graph = StoryGraph(entities={"prov_char": prov_ent})

        res = RunResult()
        res.states.append(
            StateInstance(id="inst.p", entity="prov_char", state_id="prov_char.state.base", at=StoryTime(scene_index=0, line=2), source="base")
        )
        violations = run_checks(res, test_graph, canon="hot_scoomp_main", elements=[])
        g7 = [v for v in violations if v.rule_id == "G7_AUTO_DISCOVERED"]
        self.assertTrue(len(g7) >= 1)
        self.assertEqual(g7[0].severity, "INFO")
        self.assertIn("Auto-discovered provisional", g7[0].message)


if __name__ == "__main__":
    unittest.main()
