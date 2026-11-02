"""
Media preparation utilities for narrative ingestion.
Provides offline full-length audio extraction via ffmpeg and
keyframe extraction via ffmpeg and OpenCV.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2


class MediaPrepError(Exception):
    """Raised when media extraction or ffmpeg fails."""
    pass


def extract_audio(
    media_path: str,
    output_wav_path: str,
    sample_rate: int = 16000,
    duration: Optional[float] = None,
) -> str:
    """
    Extracts a mono 16kHz uncompressed PCM WAV audio track from a video/audio file.
    Does NOT cap duration unless explicitly requested.
    """
    media_file = Path(media_path)
    if not media_file.exists():
        raise MediaPrepError(f"Media file not found: {media_path}")

    out_file = Path(output_wav_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_file),
    ]

    if duration is not None and duration > 0:
        cmd.extend(["-t", str(duration)])

    cmd.extend([
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        str(out_file),
    ])

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        raise MediaPrepError(
            f"ffmpeg audio extraction failed (code {err.returncode}):\n{err.stderr}"
        ) from err

    if not out_file.exists() or out_file.stat().st_size == 0:
        raise MediaPrepError(f"ffmpeg produced an empty or missing output: {output_wav_path}")

    return str(out_file)


def get_video_metadata(media_path: str) -> Dict[str, Any]:
    """Retrieves basic video metadata (fps, frame count, duration in seconds)."""
    cap = cv2.VideoCapture(str(media_path))
    if not cap.isOpened():
        raise MediaPrepError(f"OpenCV could not open video: {media_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    duration = frame_count / fps if fps > 0 else 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    return {
        "fps": fps,
        "frame_count": int(frame_count),
        "duration": round(duration, 3),
        "width": width,
        "height": height,
    }


def build_scene_windows_from_transcript(
    transcript_segments: List[Dict[str, Any]],
    total_duration: float,
    min_gap_sec: float = 3.0,
    max_window_sec: float = 35.0,
) -> List[Tuple[float, float]]:
    """
    Builds monotonic scene windows based on dialogue pauses and duration limits.
    Guarantees 100% coverage from 0.0 to total_duration with zero gaps.
    """
    if total_duration <= 0:
        return [(0.0, 0.0)]

    if not transcript_segments:
        # Uniform fallback windows
        windows = []
        cur = 0.0
        while cur < total_duration:
            nxt = min(total_duration, round(cur + max_window_sec, 3))
            windows.append((cur, nxt))
            cur = nxt
        return windows

    cuts: List[float] = [0.0]

    for i in range(len(transcript_segments)):
        cur_seg = transcript_segments[i]
        seg_start = cur_seg["start"]
        seg_end = cur_seg["end"]

        # Check silence gap before this segment
        last_cut = cuts[-1]
        time_since_cut = seg_end - last_cut

        # If next segment exists, check gap to next segment
        if i < len(transcript_segments) - 1:
            next_seg = transcript_segments[i + 1]
            gap = next_seg["start"] - seg_end
            if gap >= min_gap_sec and time_since_cut >= 10.0:
                cut_point = round(seg_end + gap / 2.0, 3)
                cuts.append(cut_point)
            elif time_since_cut >= max_window_sec:
                cut_point = round(seg_end, 3)
                cuts.append(cut_point)

    if cuts[-1] < total_duration:
        cuts.append(total_duration)

    # Ensure windows are strictly monotonic
    windows: List[Tuple[float, float]] = []
    for i in range(len(cuts) - 1):
        s = round(cuts[i], 3)
        e = round(cuts[i + 1], 3)
        if e > s:
            windows.append((s, e))

    if not windows:
        windows = [(0.0, total_duration)]

    return windows


def extract_keyframes_ffmpeg(
    media_path: str,
    scene_windows: List[Tuple[float, float]],
    output_dir: str,
    frames_per_scene: int = 2,
    target_width: int = 640,
) -> Dict[str, Any]:
    """
    Ultrafast keyframe extraction using ffmpeg input seeking (-ss before -i).
    Captures representative frames at scene points in milliseconds per frame.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scene_records: List[Dict[str, Any]] = []

    for idx, (start_sec, end_sec) in enumerate(scene_windows, start=1):
        scene_id = f"scene_{idx:03d}"
        dur = end_sec - start_sec
        captured_paths: List[str] = []

        if frames_per_scene <= 1 or dur <= 1.0:
            ratios = [0.5]
        else:
            ratios = [0.3, 0.7] if frames_per_scene == 2 else [
                (i + 1) / (frames_per_scene + 1) for i in range(frames_per_scene)
            ]

        for sub_idx, ratio in enumerate(ratios, start=1):
            t_sec = round(start_sec + ratio * dur, 3)
            filename = f"{scene_id}_frame_{sub_idx:02d}.jpg"
            file_dest = out_path / filename

            # ffmpeg ultrafast seek: -ss before -i
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(t_sec),
                "-i",
                str(media_path),
                "-vframes",
                "1",
                "-vf",
                f"scale={target_width}:-1",
                "-q:v",
                "2",
                str(file_dest),
            ]

            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                if file_dest.exists() and file_dest.stat().st_size > 0:
                    captured_paths.append(str(file_dest))
            except Exception:
                pass

        scene_records.append({
            "scene_id": scene_id,
            "start": start_sec,
            "end": end_sec,
            "duration": round(dur, 3),
            "frame_paths": captured_paths,
        })

    index_data = {
        "media_path": str(media_path),
        "total_scenes": len(scene_records),
        "scenes": scene_records,
    }

    index_file = out_path / "index.json"
    with open(index_file, "w", encoding="utf-8") as fh:
        json.dump(index_data, fh, indent=2)

    return index_data


def detect_scene_cuts(
    media_path: str,
    min_scene_sec: float = 2.5,
    max_scene_sec: float = 35.0,
    hist_threshold: float = 0.55,
) -> List[Tuple[float, float]]:
    """Legacy visual scene cut detector using OpenCV HSV histogram correlation."""
    meta = get_video_metadata(media_path)
    total_dur = meta["duration"]
    if total_dur <= 0:
        return [(0.0, 0.0)]

    cap = cv2.VideoCapture(str(media_path))
    if not cap.isOpened():
        return [(0.0, total_dur)]

    fps = meta["fps"]
    frame_count = meta["frame_count"]
    step_sec = 2.0  # Sample every 2.0 seconds for fast detection
    step_frames = max(1, int(fps * step_sec))

    cut_timestamps: List[float] = [0.0]
    prev_hist = None

    frame_idx = 0
    while frame_idx < frame_count:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        timestamp = round(frame_idx / fps, 3)

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        if prev_hist is not None:
            correl = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            time_since_last_cut = timestamp - cut_timestamps[-1]

            if (correl < hist_threshold and time_since_last_cut >= min_scene_sec) or (
                time_since_last_cut >= max_scene_sec
            ):
                cut_timestamps.append(timestamp)

        prev_hist = hist
        frame_idx += step_frames

    cap.release()

    if cut_timestamps[-1] < total_dur:
        if total_dur - cut_timestamps[-1] < 1.0 and len(cut_timestamps) > 1:
            cut_timestamps[-1] = total_dur
        else:
            cut_timestamps.append(total_dur)

    windows: List[Tuple[float, float]] = []
    for i in range(len(cut_timestamps) - 1):
        s = round(cut_timestamps[i], 3)
        e = round(cut_timestamps[i + 1], 3)
        if e > s:
            windows.append((s, e))

    if not windows:
        windows = [(0.0, total_dur)]

    return windows


def extract_scene_frames(
    media_path: str,
    scene_windows: List[Tuple[float, float]],
    output_dir: str,
    frames_per_scene: int = 2,
    target_width: int = 640,
) -> Dict[str, Any]:
    """Extracts scene frames (delegating to extract_keyframes_ffmpeg for maximum speed)."""
    return extract_keyframes_ffmpeg(
        media_path=media_path,
        scene_windows=scene_windows,
        output_dir=output_dir,
        frames_per_scene=frames_per_scene,
        target_width=target_width,
    )
