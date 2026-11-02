"""
Source media ingestion and behavioral extraction package.
Provides offline audio extraction, whisper transcription, frame extraction,
scene segmentation, and structured behavioral trait extraction.
"""

from narrative_composer.ingest.media_prep import (
    extract_audio,
    detect_scene_cuts,
    extract_scene_frames,
)
from narrative_composer.ingest.transcribe import AudioTranscriber
from narrative_composer.ingest.scenes import SceneSegmenter

__all__ = [
    "extract_audio",
    "detect_scene_cuts",
    "extract_scene_frames",
    "AudioTranscriber",
    "SceneSegmenter",
]
