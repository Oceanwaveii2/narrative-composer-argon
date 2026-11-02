"""
Unit tests for Character Directive Injection and Closed-Loop Generation in Milestone 5.
Verifies that:
1. ContextProjector injects behavioral directives for active characters only.
2. Inactive characters are strictly purged to preserve context budget.
3. Character alias normalization correctly matches character nodes.
4. ComposerEngine auto-loads character nodes from config/characters.
5. Soft warnings (Rule 11) do not trigger retries, but hard errors (Rules 1, 9, 10, 12) do.
6. Utterances from committed beats are recorded in the Spatial Witness Log for cross-beat Rule 10 enforcement.
"""

import unittest
from pathlib import Path
from narrative_composer.models.causal_dag import CausalDAG, StoryBeatNode, StateDelta
from narrative_composer.models.epistemic import EpistemicMatrix, NarrativeFact, FactCategory, EpistemicBelief
from narrative_composer.models.spatial_fsm import SpatialGraph, PhysicalEntity, ItemLifecycle
from narrative_composer.models.character import (
    DialecticCharacterNode,
    DialecticPole,
    DialecticTrait,
    SynthesisRule,
    Provenance,
)
from narrative_composer.compiler.context_projector import ContextProjector
from narrative_composer.compiler.composer_engine import NarrativeComposerEngine


class TestCharacterProjection(unittest.TestCase):
    def setUp(self):
        self.epistemic = EpistemicMatrix()
        self.spatial = SpatialGraph(
            character_locations={"HAYLEY": "living_room", "STELLA": "living_room"},
            items={}
        )

        # Build mock Hayley node
        self.hayley_node = DialecticCharacterNode(
            character_id="hayley",
            display_name="Hayley Smith",
            version="1.0.0",
            thesis=DialecticPole(
                pole_name="Thesis: Crunchy Activist",
                core_drive="Moral and intellectual superiority through eco-righteousness",
                vocabulary_domain=["fair-trade", "organic", "systemic oppression"],
                traits=[
                    DialecticTrait(
                        trait_id="t1",
                        category="rationalization",
                        description="framing self-indulgence as spiritual alignment",
                        recurrence_count=1,
                        confidence_score=0.9
                    )
                ]
            ),
            antithesis=DialecticPole(
                pole_name="Antithesis: Calabasas Influencer",
                core_drive="Extreme body vanity and consumer prestige",
                vocabulary_domain=["glutes", "curated", "aesthetic"],
                traits=[]
            ),
            synthesis_rules=[
                SynthesisRule(
                    rule_id="s1",
                    trigger="confronted with vanity",
                    mechanism="using activist vocabulary to defend bodily vanity",
                    example_volley="This glute expansion is anti-capitalist resistance."
                )
            ],
            kinematics=[
                DialecticTrait(
                    trait_id="k1",
                    category="kinematics",
                    description="slow, weightless strut with exaggerated hip displacement",
                    recurrence_count=2,
                    confidence_score=1.0
                )
            ],
            idiolect=[
                DialecticTrait(
                    trait_id="i1",
                    category="idiolect",
                    description="monotone vocal fry punctuated by polysyllabic activist jargon",
                    recurrence_count=2,
                    confidence_score=1.0
                )
            ],
            status_moves=[
                DialecticTrait(
                    trait_id="sm1",
                    category="status_move",
                    description="gazing past the listener while dismissing their physical frame",
                    recurrence_count=1,
                    confidence_score=0.95
                )
            ]
        )

        # Build mock Francine node
        self.francine_node = DialecticCharacterNode(
            character_id="francine",
            display_name="Francine Smith",
            version="1.0.0",
            thesis=DialecticPole(
                pole_name="Thesis: suburban mother",
                core_drive="maternal affection",
                vocabulary_domain=["baking", "sweetheart"]
            ),
            antithesis=DialecticPole(
                pole_name="Antithesis: chaotic violence",
                core_drive="feral impulses",
                vocabulary_domain=["shiv", "fight"]
            )
        )

        self.character_nodes = {
            "hayley": self.hayley_node,
            "francine": self.francine_node
        }

    def test_active_character_directive_injected(self):
        """When Hayley is in active_characters, her behavioral directive is injected."""
        beat = StoryBeatNode(
            beat_id="beat_hayley_active",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["HAYLEY", "STELLA"],
            dramatic_goal="Hayley displays her physique.",
            prerequisite_beat_ids=[]
        )

        prompt = ContextProjector.compile_beat_prompt(
            beat=beat,
            epistemic=self.epistemic,
            spatial=self.spatial,
            character_nodes=self.character_nodes
        )

        self.assertIn("--- CHARACTER BEHAVIORAL DIRECTIVES ---", prompt)
        self.assertIn("[HAYLEY SMITH BEHAVIORAL ENGINE]", prompt)
        self.assertIn("Moral and intellectual superiority", prompt)
        self.assertIn("slow, weightless strut", prompt)
        # Inactive Francine is NOT injected
        self.assertNotIn("FRANCINE SMITH BEHAVIORAL ENGINE", prompt)

    def test_inactive_character_directive_purged(self):
        """When Hayley is NOT in active_characters, no directive is injected (preserving context)."""
        beat = StoryBeatNode(
            beat_id="beat_stella_alone",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["STELLA"],
            dramatic_goal="Stella contemplates life.",
            prerequisite_beat_ids=[]
        )

        prompt = ContextProjector.compile_beat_prompt(
            beat=beat,
            epistemic=self.epistemic,
            spatial=self.spatial,
            character_nodes=self.character_nodes
        )

        self.assertNotIn("--- CHARACTER BEHAVIORAL DIRECTIVES ---", prompt)
        self.assertNotIn("HAYLEY SMITH BEHAVIORAL ENGINE", prompt)
        self.assertNotIn("FRANCINE SMITH BEHAVIORAL ENGINE", prompt)

    def test_character_alias_resolution(self):
        """Aliases like 'HAYLEY FITNESS GODDESS' resolve to 'hayley' character node."""
        beat = StoryBeatNode(
            beat_id="beat_alias_active",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["HAYLEY FITNESS GODDESS"],
            dramatic_goal="Hayley poses.",
            prerequisite_beat_ids=[]
        )

        prompt = ContextProjector.compile_beat_prompt(
            beat=beat,
            epistemic=self.epistemic,
            spatial=self.spatial,
            character_nodes=self.character_nodes
        )

        self.assertIn("--- CHARACTER BEHAVIORAL DIRECTIVES ---", prompt)
        self.assertIn("[HAYLEY SMITH BEHAVIORAL ENGINE]", prompt)

    def test_auto_load_character_from_disk(self):
        """Verifies DialecticCharacterNode.load_directory loads hayley.json from config/characters."""
        config_dir = Path(__file__).resolve().parent.parent / "config" / "characters"
        nodes = DialecticCharacterNode.load_directory(str(config_dir))
        self.assertIn("hayley", nodes)
        hayley = nodes["hayley"]
        self.assertEqual(hayley.character_id, "hayley")
        self.assertGreater(len(hayley.kinematics), 0)
        directive = hayley.to_prompt_directive(120)
        self.assertIn("BEHAVIORAL ENGINE", directive)

    def test_engine_closed_loop_repairs_rule9_namedrop(self):
        """Engine automatically catches Rule 9 source namedrop and repairs it."""
        beat = StoryBeatNode(
            beat_id="beat_rule9_repair",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["HAYLEY"],
            dramatic_goal="Hayley poses.",
            prerequisite_beat_ids=[]
        )
        dag = CausalDAG(beats={"beat_rule9_repair": beat})

        attempts = []

        def mock_llm(prompt: str) -> str:
            attempts.append(prompt)
            if len(attempts) == 1:
                # Violates Rule 9: Leaks source name 'kardashian'
                return '**HAYLEY:** "I look like a Kardashian now."'
            else:
                # Repaired
                return '**HAYLEY:** "My silhouette has achieved structural transcendence."'

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=dag,
            epistemic=self.epistemic,
            spatial=self.spatial,
            llm_generate_fn=mock_llm,
            character_nodes=self.character_nodes
        )

        output = engine.process_beat(beat, max_retries=3)
        self.assertEqual(len(attempts), 2)
        self.assertIn("RULE_9_SOURCE_NAME_EMBARGO", attempts[1])
        self.assertIn("structural transcendence", output)

    def test_engine_soft_warning_does_not_block_commit(self):
        """Rule 11 (Exposition Warning) does not trigger repair retries because severity='WARNING'."""
        beat = StoryBeatNode(
            beat_id="beat_warning_pass",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["STELLA"],
            dramatic_goal="Stella gives comedic exposition.",
            prerequisite_beat_ids=[]
        )
        dag = CausalDAG(beats={"beat_warning_pass": beat})

        call_count = [0]

        def mock_llm_with_exposition(prompt: str) -> str:
            call_count[0] += 1
            # 50 words with "let me explain" triggering Rule 11 warning
            long_line = (
                '**STELLA:** "Let me explain the situation because as you know my entire backstory '
                'is completely wild and involves multiple foreign dignitaries, three private yachts, '
                'a secret Swiss bank account, and twenty-five thousand dollars worth of imported silk '
                'that Francine accidentally washed in hot water last Tuesday afternoon."'
            )
            return long_line

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=dag,
            epistemic=self.epistemic,
            spatial=self.spatial,
            llm_generate_fn=mock_llm_with_exposition
        )

        output = engine.process_beat(beat, max_retries=2)
        # Should succeed on attempt 1 because warnings do not trigger retries
        self.assertEqual(call_count[0], 1)
        self.assertTrue(beat.is_completed)
        self.assertIn("Let me explain", output)

    def test_cross_beat_witness_log_telepathy_prevention(self):
        """Committed beat logs utterances into Spatial Witness Log, catching telepathy in beat 2."""
        spatial = SpatialGraph(
            character_locations={"HAYLEY": "living_room", "STELLA": "upstairs_bedroom"},
            items={}
        )

        beat1 = StoryBeatNode(
            beat_id="beat1",
            chunk_index=1,
            beat_order=1,
            slugline="INT. LIVING ROOM - DAY",
            active_characters=["HAYLEY"],
            dramatic_goal="Hayley coins phrase.",
            prerequisite_beat_ids=[]
        )
        beat2 = StoryBeatNode(
            beat_id="beat2",
            chunk_index=1,
            beat_order=2,
            slugline="INT. UPSTAIRS BEDROOM - DAY",
            active_characters=["STELLA"],
            dramatic_goal="Stella talks alone in bedroom.",
            prerequisite_beat_ids=["beat1"]
        )

        dag = CausalDAG(beats={"beat1": beat1, "beat2": beat2})

        b2_attempts = []

        def mock_llm(prompt: str) -> str:
            if "beat1" in prompt:
                # Hayley coins 'petroleum in your ass' in living room
                return '**HAYLEY:** "You literally put petroleum in your ass!"'
            else:
                b2_attempts.append(prompt)
                if len(b2_attempts) == 1:
                    # Stella in bedroom telepathically quotes Hayley's phrase
                    return '**STELLA:** "Did someone say petroleum in your ass?"'
                else:
                    return '**STELLA:** "I feel a strange chill up here."'

        engine = NarrativeComposerEngine(
            review_fn=lambda proposal: True,  # Explicit fixture reviewer; default remains pending.
            dag=dag,
            epistemic=self.epistemic,
            spatial=spatial,
            llm_generate_fn=mock_llm
        )

        final_script = engine.run_pipeline(max_retries=3)
        self.assertEqual(len(b2_attempts), 2, "Beat 2 should trigger auto-repair due to telepathy violation")
        self.assertIn("RULE_10_TELEPATHIC_PHRASE_LEAK", b2_attempts[1])
        self.assertIn("strange chill up here", final_script)


if __name__ == "__main__":
    unittest.main()
