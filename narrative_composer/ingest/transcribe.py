"""
Offline audio transcription module using faster-whisper.
Produces timestamped transcript.jsonl files with monotonic timecodes.
"""

import json
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from faster_whisper import WhisperModel


def load_audio_as_numpy(wav_path: Path) -> np.ndarray:
    """Loads a 16kHz mono 16-bit PCM WAV into float32 numpy array, avoiding PyAV container bugs."""
    with wave.open(str(wav_path), "rb") as wf:
        n_frames = wf.getnframes()
        frames = wf.readframes(n_frames)
        return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


class TranscriptionError(Exception):
    """Raised when transcription fails."""
    pass


class AudioTranscriber:
    """
    Offline local speech-to-text transcriber using faster-whisper.
    Defaults to device='cpu' with compute_type='int8' for guaranteed compatibility.
    """

    def __init__(
        self,
        model_size_or_path: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size_or_path = model_size_or_path
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            try:
                self._model = WhisperModel(
                    self.model_size_or_path,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception as err:
                raise TranscriptionError(
                    f"Failed to load Whisper model '{self.model_size_or_path}': {err}"
                ) from err
        return self._model

    def transcribe(
        self,
        audio_path: str,
        output_jsonl_path: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Transcribes the given audio file and returns a list of segments.
        If output_jsonl_path is provided, writes records to JSONL.
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        try:
            # If input is a WAV file, load directly via numpy to bypass PyAV bugs
            if audio_file.suffix.lower() == ".wav":
                audio_input = load_audio_as_numpy(audio_file)
            else:
                audio_input = str(audio_file)

            segments, info = self.model.transcribe(
                audio_input,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=False,
            )

            records: List[Dict[str, Any]] = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                records.append({
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": text,
                })

        except Exception as err:
            raise TranscriptionError(f"Whisper transcription failed on {audio_path}: {err}") from err

        if output_jsonl_path:
            out_file = Path(output_jsonl_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as fh:
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        return records

    @staticmethod
    def load_transcript(jsonl_path: str) -> List[Dict[str, Any]]:
        """Reads a saved transcript.jsonl file into memory."""
        path = Path(jsonl_path)
        if not path.exists():
            raise TranscriptionError(f"Transcript file not found: {jsonl_path}")

        records: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
