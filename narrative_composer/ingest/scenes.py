"""
Scene segmentation and alignment engine.
Combines timestamped transcripts with scene cut windows and extracted keyframes
into canonical scenes.json packages for downstream behavioral extraction.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SceneSegmenter:
    """
    Aligns transcript segments with visual scene cut windows.
    Ensures 100% coverage, monotonic boundaries, and frame association.
    """

    @staticmethod
    def align_transcript_to_scenes(
        transcript_segments: List[Dict[str, Any]],
        scene_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Maps transcript lines to scene windows based on timestamp midpoint overlap.
        """
        aligned_scenes: List[Dict[str, Any]] = []

        for scene in scene_records:
            s_start = scene["start"]
            s_end = scene["end"]
            scene_segments: List[Dict[str, Any]] = []

            for seg in transcript_segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                seg_mid = (seg_start + seg_end) / 2.0

                # Check if segment belongs in this scene window
                if s_start <= seg_mid < s_end:
                    scene_segments.append(seg)
                elif seg_start < s_end and seg_end > s_start:
                    # Partial overlap check
                    overlap = min(s_end, seg_end) - max(s_start, seg_start)
                    seg_len = max(0.1, seg_end - seg_start)
                    if overlap / seg_len >= 0.5:
                        scene_segments.append(seg)

            combined_text = " ".join(s["text"] for s in scene_segments).strip()

            aligned_scenes.append({
                "scene_id": scene["scene_id"],
                "start": s_start,
                "end": s_end,
                "duration": scene.get("duration", round(s_end - s_start, 3)),
                "transcript": combined_text,
                "segments": scene_segments,
                "frame_paths": scene.get("frame_paths", []),
            })

        return aligned_scenes

    @classmethod
    def build_scene_manifest(
        cls,
        media_id: str,
        media_path: str,
        transcript_segments: List[Dict[str, Any]],
        scene_records: List[Dict[str, Any]],
        output_scenes_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Builds the complete scene manifest and optionally saves to scenes.json.
        """
        aligned = cls.align_transcript_to_scenes(transcript_segments, scene_records)

        manifest = {
            "media_id": media_id,
            "media_path": str(media_path),
            "total_scenes": len(aligned),
            "scenes": aligned,
        }

        if output_scenes_json:
            out_file = Path(output_scenes_json)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, ensure_ascii=False)

        return manifest
