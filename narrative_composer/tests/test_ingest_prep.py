"""
Unit tests for Milestone 1: Local media prep & transcription pipeline.
Verifies audio extraction, scene window monotonicity, keyframe indexing,
and transcript-to-scene alignment.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from narrative_composer.ingest.media_prep import (
    MediaPrepError,
    detect_scene_cuts,
    extract_audio,
    extract_scene_frames,
    get_video_metadata,
)
from narrative_composer.ingest.scenes import SceneSegmenter
from narrative_composer.ingest.transcribe import AudioTranscriber, TranscriptionError


class TestMediaPrepAndScenes(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extract_audio_missing_file_raises(self):
        with self.assertRaises(MediaPrepError):
            extract_audio("non_existent_file.mp4", str(self.work_dir / "out.wav"))

    @patch("subprocess.run")
    def test_extract_audio_invokes_ffmpeg_correctly(self, mock_run):
        # Create a dummy source file
        dummy_src = self.work_dir / "test.mp4"
        dummy_src.write_text("fake video content")
        dummy_out = self.work_dir / "out.wav"

        # Mock subprocess run to create the output file so stat check passes
        def fake_run(cmd, **kwargs):
            dummy_out.write_text("fake wav content")
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_run

        out = extract_audio(str(dummy_src), str(dummy_out), sample_rate=16000)
        self.assertEqual(out, str(dummy_out))
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("ffmpeg", cmd)
        self.assertIn("-ar", cmd)
        self.assertIn("16000", cmd)
        self.assertIn("-ac", cmd)
        self.assertIn("1", cmd)

    def test_scene_segmenter_alignment_monotonic_and_complete(self):
        # 3 scene windows covering 0.0 -> 30.0 s
        scene_records = [
            {"scene_id": "scene_001", "start": 0.0, "end": 10.0, "frame_paths": ["f1.jpg"]},
            {"scene_id": "scene_002", "start": 10.0, "end": 20.0, "frame_paths": ["f2.jpg"]},
            {"scene_id": "scene_003", "start": 20.0, "end": 30.0, "frame_paths": ["f3.jpg"]},
        ]

        # 4 transcript segments
        transcript_segments = [
            {"start": 1.0, "end": 4.5, "text": "Welcome to the fitness sanctuary."},
            {"start": 5.0, "end": 8.5, "text": "Feel the holy burn in your glutes."},
            {"start": 11.0, "end": 16.0, "text": "Wait, my rear end is inflating exponentially!"},
            {"start": 22.0, "end": 28.0, "text": "This bamboo fabric can't hold this mass!"},
        ]

        manifest = SceneSegmenter.build_scene_manifest(
            media_id="test_media",
            media_path="/path/to/test.mp4",
            transcript_segments=transcript_segments,
            scene_records=scene_records,
            output_scenes_json=str(self.work_dir / "scenes.json"),
        )

        self.assertEqual(manifest["total_scenes"], 3)
        scenes = manifest["scenes"]

        # Check scene 1 has the two early lines
        self.assertEqual(len(scenes[0]["segments"]), 2)
        self.assertIn("fitness sanctuary", scenes[0]["transcript"])
        self.assertIn("holy burn", scenes[0]["transcript"])

        # Check scene 2 has the inflation line
        self.assertEqual(len(scenes[1]["segments"]), 1)
        self.assertIn("inflating exponentially", scenes[1]["transcript"])

        # Check scene 3 has the bamboo line
        self.assertEqual(len(scenes[2]["segments"]), 1)
        self.assertIn("bamboo fabric", scenes[2]["transcript"])

        # Check monotonic coverage
        for i in range(len(scenes)):
            self.assertGreater(scenes[i]["end"], scenes[i]["start"])
            if i > 0:
                self.assertEqual(scenes[i]["start"], scenes[i - 1]["end"])

        # Verify output file exists and loads
        self.assertTrue((self.work_dir / "scenes.json").exists())
        with open(self.work_dir / "scenes.json", "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
            self.assertEqual(loaded["media_id"], "test_media")

    def test_transcribe_load_jsonl(self):
        jsonl_path = self.work_dir / "test_transcript.jsonl"
        items = [
            {"start": 0.0, "end": 2.5, "text": "Line one."},
            {"start": 3.0, "end": 5.5, "text": "Line two."},
        ]
        with open(jsonl_path, "w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item) + "\n")

        loaded = AudioTranscriber.load_transcript(str(jsonl_path))
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["text"], "Line one.")
        self.assertEqual(loaded[1]["text"], "Line two.")


if __name__ == "__main__":
    unittest.main()
