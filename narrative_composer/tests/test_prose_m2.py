"""
Milestone 2 Test Suite for Noir Module 1 Prose Diagnostics.
Verifies:
1. Filter word detection ('she noticed', 'he saw', 'she felt').
2. Emotion label syntax detection ('said angrily', 'in sheer frustration', adjective piles).
3. Cadence and burstiness scoring (monotony warnings on uniform sentence lengths).
4. Sensory detail budgeting (olfactory, auditory, tactile, visual specific).
5. Psychic distance estimation (John Gardner 1-5 scale).
6. Deterministic execution speed and zero false-positive regressions on clean prose.
"""

import unittest
from narrative_composer.prose.diagnostics import ProseDiagnosticsAnalyzer


class TestProseMilestone2(unittest.TestCase):
    """Test suite covering M2 prose diagnostics."""

    def test_01_filter_word_detection(self):
        """Detects observer filter words and issues actionable warning."""
        flawed_prose = (
            "Hayley noticed her arms were tingling. She could see white sparks dying on the carpet. "
            "Then she felt the strange rush of motor oil and flax under her skin."
        )
        report = ProseDiagnosticsAnalyzer.analyze(flawed_prose, span_id="beat-hayley-scratch")

        self.assertEqual(report.filter_word_count, 3)
        self.assertIn("noticed", report.filter_words_found[0])
        self.assertIn("could see", report.filter_words_found[1])
        self.assertIn("felt", report.filter_words_found[2])
        self.assertTrue(any("Filter words detected" in w for w in report.warnings))

        # Clean prose without observer filters
        clean_prose = (
            "White sparks snapped off Hayley's wrists and died in the carpet. "
            "Her fingernails tore through the neon tie-dye, scratching skin raw."
        )
        clean_report = ProseDiagnosticsAnalyzer.analyze(clean_prose, span_id="beat-clean")
        self.assertEqual(clean_report.filter_word_count, 0)
        self.assertEqual(len(clean_report.filter_words_found), 0)
        self.assertFalse(any("Filter words detected" in w for w in clean_report.warnings))

    def test_02_emotion_label_syntax(self):
        """Flags dialogue tag adverbs, explicit emotion labels, and adjective piles."""
        label_prose = (
            '"Stop looking at me!" Hayley said angrily. '
            'Stella stared back in pure frustration, her voice was full of malice.'
        )
        report = ProseDiagnosticsAnalyzer.analyze(label_prose, span_id="beat-tags")

        self.assertTrue(report.label_syntax_detected)
        self.assertTrue(any("said angrily" in ex.lower() for ex in report.label_examples))
        self.assertTrue(any("in pure frustration" in ex.lower() for ex in report.label_examples))
        self.assertTrue(any("Emotion label syntax detected" in w for w in report.warnings))

        # Adjective pile detection
        pile_prose = "She flaunted her massive, shiny, impossibly gigantic, glistening peach."
        pile_report = ProseDiagnosticsAnalyzer.analyze(pile_prose, span_id="beat-pile")
        self.assertTrue(pile_report.label_syntax_detected)
        self.assertTrue(any("Adjective pile" in ex for ex in pile_report.label_examples))

    def test_03_cadence_and_burstiness(self):
        """Accurately calculates burstiness and flags monotonous sentence lengths."""
        # Monotonous: 3 sentences of exactly 6 words each
        monotonous_prose = (
            "Hayley stood in the pink room. "
            "Stella sat on the velvet couch. "
            "Gloria stood on the wooden table."
        )
        mono_report = ProseDiagnosticsAnalyzer.analyze(monotonous_prose, span_id="beat-mono")
        self.assertAlmostEqual(mono_report.burstiness_score, 0.0, places=1)
        self.assertTrue(any("Monotonous cadence detected" in w for w in mono_report.warnings))

        # Bursting: short punches mixed with longer descriptive clauses
        bursty_prose = (
            "White sparks snapped. "
            "Hayley whirled around in outrage, her massive tie-dye backside swinging wide across the living room carpet. "
            "Gloria wobbled. Crash."
        )
        bursty_report = ProseDiagnosticsAnalyzer.analyze(bursty_prose, span_id="beat-bursty")
        self.assertGreater(bursty_report.burstiness_score, 4.0)
        self.assertFalse(any("Monotonous cadence detected" in w for w in bursty_report.warnings))

    def test_04_sensory_budget_counting(self):
        """Counts concrete sensory anchors across olfactory, tactile, auditory, and visual domains."""
        rich_prose = (
            "The living room smelled of ozone and damp lavender. "
            "Hayley scratched her raw arms as white sparks snapped against the neon tie-dye."
        )
        report = ProseDiagnosticsAnalyzer.analyze(rich_prose, span_id="beat-sensory")

        # ozone, lavender (olfactory); scratch/scratched, raw, sparks (tactile); snapped (auditory); neon, tie-dye (visual)
        self.assertGreaterEqual(report.sensory_details_count, 4)
        self.assertFalse(any("Sensory deficit" in w for w in report.warnings))

        # Abstract, sensory-deprived prose
        abstract_prose = (
            "She considered the situation carefully. "
            "The implications were entirely unacceptable from an ideological standpoint."
        )
        abstract_report = ProseDiagnosticsAnalyzer.analyze(abstract_prose, span_id="beat-abstract")
        self.assertEqual(abstract_report.sensory_details_count, 0)
        self.assertTrue(any("Sensory deficit" in w for w in abstract_report.warnings))

    def test_05_psychic_distance_estimation(self):
        """Estimates narrator proximity on a 1-5 scale and flags divergence."""
        # Level 1 / 2: Close sensory action
        close_prose = (
            "Her fingernails tore into neon tie-dye. "
            "White sparks crackled off her wrists, smelling of ozone and ruined lavender."
        )
        close_report = ProseDiagnosticsAnalyzer.analyze(
            close_prose, span_id="beat-close", target_psychic_distance=2
        )
        self.assertIn(close_report.psychic_distance_estimate, [1, 2])
        self.assertFalse(any("Psychic distance divergence" in w for w in close_report.warnings))

        # Level 4 / 5: Distant summary with filter words and emotion labels
        distant_prose = (
            "Hayley noticed that her sister was being unkind. "
            "She observed that Stella seemed to be in pure frustration, "
            "which Hayley felt was completely unfair."
        )
        distant_report = ProseDiagnosticsAnalyzer.analyze(
            distant_prose, span_id="beat-distant", target_psychic_distance=2
        )
        self.assertGreaterEqual(distant_report.psychic_distance_estimate, 4)
        self.assertTrue(any("Psychic distance divergence" in w for w in distant_report.warnings))


if __name__ == "__main__":
    unittest.main()
