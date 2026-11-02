"""Tests for ingesting a new story: adaptation, conditioning, and artifact generation."""

import json
import tempfile
import unittest
from pathlib import Path

from narrative_composer.story import adapt_story, condition_text, run_story

SOURCE = """# TEST TITLE

### Production Bible
This dossier should be dropped.

## PART I: ENGLISH SCRIPT

### MOVEMENT I — START

Rainee walks into the lobby.

**RAINEE**
Hello there.

**SMACK!**

**[CONTAMINANTS: 0.0%]**

[VIRTUAL MONITOR: DIAGNOSTIC SCAN]

**蕾妮**
你好。
"""


class TestStoryAdapter(unittest.TestCase):
    def test_adapts_cues_sfx_annotations_and_headings(self):
        adapted, stats = adapt_story(SOURCE)

        self.assertIn("**RAINEE:**", adapted)
        self.assertIn("**蕾妮:**", adapted)
        self.assertIn("> SFX: SMACK!", adapted)
        self.assertIn("> [CONTAMINANTS: 0.0%]", adapted)
        self.assertIn("[VIRTUAL MONITOR: DIAGNOSTIC SCAN]", adapted)
        self.assertIn("## MOVEMENT I — START", adapted)
        self.assertIn("# TEST TITLE", adapted)
        self.assertNotIn("Production Bible", adapted, "front matter dossier should be dropped")
        self.assertEqual(stats["cues"], 2)
        self.assertEqual(stats["sfx"], 1)
        self.assertEqual(stats["annotations"], 1)

    def test_conditioning_strips_emphasis_and_filter_phrases(self):
        text = "She *smiled* at him. Across the floor, Toodles caught sight of her."
        conditioned, metrics = condition_text(text)

        self.assertNotIn("*", conditioned)
        self.assertIn("spotted", conditioned)
        self.assertEqual(metrics["filter_fixes"], 1)
        self.assertEqual(metrics["filter_words"], 0)

    def test_run_story_writes_all_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.md"
            source.write_text(SOURCE, encoding="utf-8")
            out = Path(tmp) / "out"

            report = run_story(source, out, title="Test Story", canon="test_canon")

            self.assertTrue((out / "reader.html").exists())
            self.assertTrue((out / "nodes.json").exists())
            self.assertTrue((out / "report.json").exists())
            self.assertTrue((out / "story.md").exists())
            self.assertEqual((out / 'story.md').read_bytes(),source.read_bytes())
            self.assertEqual(report['conditioning']['status'],'not run; propose and review separately')
            self.assertIn("rainee", report["entities"])
            self.assertGreater(report["summary"]["nodes"], 0)

            reader = (out / "reader.html").read_text(encoding="utf-8")
            self.assertIn("character-cue", reader)
            self.assertIn("你好", reader)

            saved = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["story"], "Test Story")


if __name__ == "__main__":
    unittest.main()
