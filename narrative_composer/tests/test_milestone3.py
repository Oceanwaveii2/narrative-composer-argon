"""
Milestone 3 Test Suite: Context Projector, Closed-Loop Engine & Auto-Repair Loop.
Runs via standard library unittest.
"""

import unittest
from narrative_composer.models.causal_dag import CausalDAG, StoryBeatNode, StateDelta
from narrative_composer.models.epistemic import EpistemicMatrix, NarrativeFact, FactCategory, EpistemicBelief
from narrative_composer.models.spatial_fsm import SpatialGraph, PhysicalEntity, ItemLifecycle
from narrative_composer.compiler.context_projector import ContextProjector
from narrative_composer.compiler.composer_engine import NarrativeComposerEngine


class TestContextProjector(unittest.TestCase):
    def setUp(self):
        self.epistemic = EpistemicMatrix()
        self.epistemic.facts["fact_steve"] = NarrativeFact(
            fact_id="fact_steve",
            category=FactCategory.IDENTITY,
            canonical_text="Francine wishes she had a son named Steve.",
            embargo_tokens=["Steve", "Steven"]
        )
        self.epistemic.set_belief("STELLA", "fact_steve", EpistemicBelief.UNKNOWN)

        self.spatial = SpatialGraph(
            character_locations={"STELLA": "living_room"},
            items={
                "gloria_lamp": PhysicalEntity(
                    item_id="gloria_lamp",
                    name="Gloria the Flamingo Lamp",
                    lifecycle=ItemLifecycle.DORMANT,
                    room_id="living_room"
                ),
                "nail_file": PhysicalEntity(
                    item_id="nail_file",
                    name="Zooey's Nail File",
                    lifecycle=ItemLifecycle.DRAWN,
                    room_id="upstairs_bedroom",
                    held_by="ZOOEY"
                )
            }
        )
        self.beat = StoryBeatNode(
            beat_id="beat_test_roast",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - NIGHT",
            active_characters=["STELLA"],
            dramatic_goal="Stella roasts the workout equipment.",
            prerequisite_beat_ids=[]
        )

    def test_compile_beat_prompt_structure(self):
        prompt = ContextProjector.compile_beat_prompt(
            beat=self.beat,
            epistemic=self.epistemic,
            spatial=self.spatial,
            prior_dialogue_tail="HAYLEY: Look at my glutes!"
        )
        # 1. Contains slugline and dramatic goal
        self.assertIn("INT. LIVING ROOM - NIGHT", prompt)
        self.assertIn("Stella roasts the workout equipment.", prompt)

        # 2. Contains room prop Gloria, but NOT bedroom nail file
        self.assertIn("Gloria the Flamingo Lamp", prompt)
        self.assertNotIn("Zooey's Nail File", prompt)

        # 3. Contains active embargo for Steve
        self.assertIn("EMBARGOED TOKENS:", prompt)
        self.assertIn("steve", prompt.lower())

        # 4. Unknown secret fact is NOT listed in Stella's established knowledge
        self.assertIn("[STELLA ESTABLISHED KNOWLEDGE]", prompt)
        self.assertIn("No knowledge facts have been modeled", prompt)
        self.assertNotIn("HG studio secrets", prompt)
        self.assertNotIn("petty sisterly roasts", prompt)
        self.assertNotIn("Physical Slapstick", prompt)


class TestComposerEngineClosedLoop(unittest.TestCase):
    def setUp(self):
        self.epistemic = EpistemicMatrix()
        self.epistemic.facts["fact_steve"] = NarrativeFact(
            fact_id="fact_steve",
            category=FactCategory.IDENTITY,
            canonical_text="Steve identity reveal",
            embargo_tokens=["Steve", "Steven"]
        )
        self.epistemic.set_belief("STELLA", "fact_steve", EpistemicBelief.UNKNOWN)

        self.spatial = SpatialGraph(
            character_locations={"STELLA": "living_room", "HAYLEY": "living_room"},
            items={
                "gloria_lamp": PhysicalEntity(
                    item_id="gloria_lamp",
                    name="Gloria the Flamingo Lamp",
                    lifecycle=ItemLifecycle.DORMANT,
                    room_id="living_room"
                ),
                "stella_polo_buttons": PhysicalEntity(
                    item_id="stella_polo_buttons",
                    name="Stella's Polo Buttons",
                    lifecycle=ItemLifecycle.EQUIPPED,
                    room_id="living_room",
                    held_by="STELLA",
                    charges_remaining=6,
                    max_charges=6
                )
            }
        )

        self.beat1 = StoryBeatNode(
            beat_id="beat_1_break_lamp",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - NIGHT",
            active_characters=["STELLA", "HAYLEY"],
            dramatic_goal="Hayley smashes Gloria the Flamingo Lamp; top 2 buttons pop.",
            prerequisite_beat_ids=[],
            state_delta=StateDelta(
                prop_mutations=[
                    {"item_id": "gloria_lamp", "lifecycle": "destroyed"},
                    {"item_id": "stella_polo_buttons", "charges_delta": -2}
                ]
            )
        )

        self.beat2 = StoryBeatNode(
            beat_id="beat_2_react",
            chunk_index=1,
            beat_order=2,
            slugline="INT. LIVING ROOM - CONTINUOUS",
            active_characters=["STELLA", "HAYLEY"],
            dramatic_goal="Stella reacts to the broken lamp.",
            prerequisite_beat_ids=["beat_1_break_lamp"]
        )

        self.dag = CausalDAG(beats={
            "beat_1_break_lamp": self.beat1,
            "beat_2_react": self.beat2
        })

    def test_closed_loop_auto_repair_recovery(self):
        """
        Simulates an LLM that fails on attempt 1 by uttering an embargoed token,
        then reads the repair prompt and fixes it on attempt 2.
        """
        attempts = []

        def mock_llm_generator(prompt: str) -> str:
            attempts.append(prompt)
            if len(attempts) == 1:
                # Attempt 1: Violates Rule 1 (Token Embargo)
                return '**STELLA:** "Steve would never let you get away with this!"'
            else:
                # Attempt 2: Fixed
                return '**STELLA:** "Mom Rainee would never let you get away with this!"'

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=self.dag,
            epistemic=self.epistemic,
            spatial=self.spatial,
            llm_generate_fn=mock_llm_generator
        )

        # Process Beat 1
        output = engine.process_beat(self.beat1, max_retries=3)

        # Assertions
        self.assertEqual(len(attempts), 2, "Engine should have triggered exactly 1 repair retry")
        self.assertIn("CRITICAL CONTINUITY VIOLATIONS DETECTED", attempts[1])
        self.assertIn("RULE_1_FORBIDDEN_TOKEN_EMBARGO", attempts[1])
        self.assertIn("Mom Rainee would never", output)

        # Verify State Delta was applied upon commit
        self.assertTrue(self.beat1.is_completed)
        self.assertEqual(self.spatial.items["gloria_lamp"].lifecycle, ItemLifecycle.DESTROYED)
        self.assertEqual(self.spatial.items["stella_polo_buttons"].charges_remaining, 4)

    def test_empty_punch_up_preserves_original_review_candidate(self):
        from narrative_composer.compiler.composer_engine import PendingBeatReview
        outputs = iter(['The room is quiet.', ''])
        engine = NarrativeComposerEngine(dag=self.dag, epistemic=self.epistemic, spatial=self.spatial,
                                         llm_generate_fn=lambda _prompt: next(outputs))
        with self.assertRaises(PendingBeatReview) as pending:
            engine.process_beat(self.beat1, punch_up=True)
        self.assertEqual(pending.exception.proposal['text'], 'The room is quiet.')
        self.assertFalse(self.beat1.is_completed)

    def test_multi_beat_dag_execution(self):
        """Verifies full execution of sequential beats through the engine."""
        call_count = [0]

        def compliant_mock_llm(prompt: str) -> str:
            call_count[0] += 1
            if "beat_1_break_lamp" in prompt:
                return '**HAYLEY:** "Take that, Gloria!"\n\n*Gloria the Flamingo Lamp shatters.*'
            else:
                return '**STELLA:** "You broke Gloria!"'

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=self.dag,
            epistemic=self.epistemic,
            spatial=self.spatial,
            llm_generate_fn=compliant_mock_llm
        )

        final_script = engine.run_pipeline()
        self.assertEqual(call_count[0], 2)
        self.assertTrue(self.dag.is_all_completed())
        self.assertIn("Take that, Gloria!", final_script)
        self.assertIn("You broke Gloria!", final_script)

    def test_exceeded_max_retries_raises_error(self):
        """Verifies that persistent violations raise a RuntimeError after max_retries."""
        def persistent_failing_llm(prompt: str) -> str:
            return '**STELLA:** "Steve Steve Steve!"'

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=self.dag,
            epistemic=self.epistemic,
            spatial=self.spatial,
            llm_generate_fn=persistent_failing_llm
        )

        with self.assertRaises(RuntimeError) as ctx:
            engine.process_beat(self.beat1, max_retries=2)

        self.assertIn("failed verification after 2 attempts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
