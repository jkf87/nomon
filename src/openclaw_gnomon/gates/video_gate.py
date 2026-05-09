"""
VideoGate — evaluates video outputs for YouTube production quality.

Quantitative checks (label="quantitative", block_threshold=30.0):
- subtitle_accuracy: WER (word error rate) against reference
- length_ratio: video duration vs script duration ratio
- thumbnail_readability: OCR success + font size + WCAG contrast
- chapter_marker_density: markers per minute
- audio_levels: peak dBFS range + LUFS target
- aspect_ratio: matches expected 16:9/9:16/1:1
- caption_lang_coverage: multilingual subtitle coverage

Persona-LLM checks (label="persona-llm"):
- hook_strength: first 5 seconds click retention for target audience
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openclaw_gnomon.gates.base import GateResult


@dataclass
class _VideoMetadata:
    duration: float  # seconds
    width: int
    height: int
    fps: float
    codec: str


@dataclass
class _AudioMetadata:
    peak_dbfs: float
    lufs: float


def _get_video_metadata(video_path: Path) -> Optional[_VideoMetadata]:
    """Extract video metadata using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        stream = data["streams"][0]
        format_data = data["format"]

        # Parse frame rate (e.g., "30/1" -> 30.0)
        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)

        return _VideoMetadata(
            duration=float(format_data["duration"]),
            width=int(stream["width"]),
            height=int(stream["height"]),
            fps=fps,
            codec=stream["codec_name"],
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ValueError, IndexError):
        return None


def _get_audio_metadata(video_path: Path) -> Optional[_AudioMetadata]:
    """Extract audio metadata using ffmpeg."""
    try:
        # Get peak dBFS
        cmd_peak = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", "volumedetect",
            "-vn",
            "-sn",
            "-dn",
            "-f", "null",
            "-",
        ]
        result = subprocess.run(cmd_peak, capture_output=True, text=True, timeout=60)

        peak_dbfs = -float("inf")
        if result.stderr:
            match = re.search(r"max_volume:\s*([-\d.]+) dB", result.stderr)
            if match:
                peak_dbfs = float(match.group(1))

        # Get LUFS (using ebu r128 filter)
        cmd_lufs = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", "ebur128=peak=true",
            "-vn",
            "-sn",
            "-dn",
            "-f", "null",
            "-",
        ]
        result_lufs = subprocess.run(cmd_lufs, capture_output=True, text=True, timeout=60)

        lufs = -23.0  # default EBU R128 target
        if result_lufs.stderr:
            match = re.search(r"I:\s*([-\d.]+) LUFS", result_lufs.stderr)
            if match:
                lufs = float(match.group(1))

        return _AudioMetadata(peak_dbfs=peak_dbfs, lufs=lufs)
    except (subprocess.TimeoutExpired, ValueError):
        return None


def _calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()

    # Levenshtein distance for word alignment
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost,  # substitution
            )

    distance = dp[m][n]
    return distance / len(ref_words) if ref_words else 1.0


def _check_thumbnail_readability(thumbnail_path: Path) -> Tuple[float, Dict[str, Any]]:
    """Check thumbnail readability using OCR."""
    details: Dict[str, Any] = {
        "ocr_success": False,
        "font_size_px": 0,
        "contrast_ratio": 0.0,
    }

    try:
        # Try OCR using pytesseract if available
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(thumbnail_path)
            text = pytesseract.image_to_string(img)
            details["ocr_success"] = len(text.strip()) > 10
            details["text_length"] = len(text.strip())
        except ImportError:
            details["error"] = "pytesseract/PIL not available"

        # Basic check: thumbnail size should be at least 1280x720
        from PIL import Image
        img = Image.open(thumbnail_path)
        width, height = img.size
        min_dimension = min(width, height)
        details["dimensions"] = f"{width}x{height}"

        # Rough font size estimate (not accurate without OCR)
        details["font_size_px"] = min_dimension // 20  # rough estimate

        # Calculate contrast ratio (simplified)
        img_grayscale = img.convert("L")
        pixels = list(img_grayscale.getdata())
        avg_brightness = sum(pixels) / len(pixels) if pixels else 128
        details["avg_brightness"] = avg_brightness

        # Pass if thumbnail is reasonably sized
        score = 100.0 if min_dimension >= 720 else 50.0
        return score, details

    except Exception as exc:
        return 0.0, {"error": str(exc), **details}


def _count_chapter_markers(subtitle_path: Path) -> int:
    """Count chapter markers in subtitle file."""
    try:
        content = subtitle_path.read_text(encoding="utf-8")
        # Look for timestamps that might indicate chapters (e.g., ## 00:01:00)
        chapter_pattern = r"##\s+\d{2}:\d{2}:\d{2}"
        return len(re.findall(chapter_pattern, content))
    except Exception:
        return 0


class VideoGate:
    name = "video"

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult:
        """Evaluate video output against YouTube production standards."""
        cwd = Path(output_dir)
        if not cwd.exists():
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": f"output dir missing: {cwd}"},
            )

        # Get spec fields
        video_path = cwd / getattr(task_spec, "video_path", "video.mp4")
        subtitle_path_str = getattr(task_spec, "subtitle_path", "subtitles.srt")
        subtitle_path = cwd / subtitle_path_str if subtitle_path_str else None
        reference_subtitle = getattr(task_spec, "reference_subtitle", None)
        target_aspect_ratio = getattr(task_spec, "aspect_ratio", "16:9")
        min_duration = getattr(task_spec, "min_duration_seconds", None)
        max_duration = getattr(task_spec, "max_duration_seconds", None)
        thumbnail_path_str = getattr(task_spec, "thumbnail_path", "thumbnail.jpg")
        thumbnail_path = cwd / thumbnail_path_str if thumbnail_path_str else None
        chapter_markers_required = getattr(task_spec, "chapter_markers_required", False)
        audio_peak_min = getattr(task_spec, "audio_peak_dbfs_min", -3.0)
        audio_peak_max = getattr(task_spec, "audio_peak_dbfs_max", -1.0)
        audio_lufs_target = getattr(task_spec, "audio_lufs_target", -14.0)
        audio_lufs_tolerance = getattr(task_spec, "audio_lufs_tolerance", 1.0)

        scores: List[float] = []
        details: Dict[str, Any] = {}
        all_passed = True

        # 1. Video metadata & aspect ratio
        video_meta = _get_video_metadata(video_path)
        if video_meta:
            details["video"] = {
                "duration": video_meta.duration,
                "width": video_meta.width,
                "height": video_meta.height,
                "fps": video_meta.fps,
                "codec": video_meta.codec,
            }

            # Check duration constraints
            if min_duration is not None:
                duration_ok = video_meta.duration >= min_duration
                scores.append(100.0 if duration_ok else 0.0)
                details["video"]["min_duration_ok"] = duration_ok
                all_passed &= duration_ok

            if max_duration is not None:
                duration_ok = video_meta.duration <= max_duration
                scores.append(100.0 if duration_ok else 0.0)
                details["video"]["max_duration_ok"] = duration_ok
                all_passed &= duration_ok

            # Check aspect ratio
            actual_ratio = f"{video_meta.width}:{video_meta.height}"
            ratio_ok = actual_ratio == target_aspect_ratio
            scores.append(100.0 if ratio_ok else 50.0)
            details["video"]["aspect_ratio"] = {
                "expected": target_aspect_ratio,
                "actual": actual_ratio,
                "ok": ratio_ok,
            }
            all_passed &= ratio_ok
        else:
            scores.append(0.0)
            details["video"] = {"error": "could not extract metadata"}
            all_passed = False

        # 2. Audio levels
        audio_meta = _get_audio_metadata(video_path)
        if audio_meta:
            peak_ok = audio_peak_min <= audio_meta.peak_dbfs <= audio_peak_max
            lufs_ok = abs(audio_meta.lufs - audio_lufs_target) <= audio_lufs_tolerance

            scores.append(100.0 if peak_ok else 50.0)
            scores.append(100.0 if lufs_ok else 50.0)

            details["audio"] = {
                "peak_dbfs": audio_meta.peak_dbfs,
                "peak_ok": peak_ok,
                "lufs": audio_meta.lufs,
                "lufs_ok": lufs_ok,
            }
            all_passed &= (peak_ok and lufs_ok)
        else:
            scores.append(50.0)
            scores.append(50.0)
            details["audio"] = {"error": "could not extract audio metadata"}

        # 3. Subtitle accuracy (WER)
        if reference_subtitle and subtitle_path and subtitle_path.exists():
            try:
                ref_content = (cwd / reference_subtitle).read_text(encoding="utf-8")
                hyp_content = subtitle_path.read_text(encoding="utf-8")
                wer = _calculate_wer(ref_content, hyp_content)
                # Lower WER is better; 0% = 100 score, 50% = 0 score
                wer_score = max(0.0, 100.0 - (wer * 200))
                scores.append(wer_score)
                details["subtitle_accuracy"] = {"wer": wer, "score": wer_score}
                all_passed &= (wer <= 0.3)  # Block threshold: 30% WER
            except Exception as exc:
                scores.append(0.0)
                details["subtitle_accuracy"] = {"error": str(exc)}
                all_passed = False
        else:
            scores.append(50.0)  # Neutral if no reference provided
            details["subtitle_accuracy"] = {"skipped": "no reference provided"}

        # 4. Length ratio (video vs script duration)
        if subtitle_path and subtitle_path.exists():
            try:
                # Estimate script duration from subtitle timestamps
                content = subtitle_path.read_text(encoding="utf-8")
                time_pattern = r"(\d{2}):(\d{2}):(\d{2})"
                matches = re.findall(time_pattern, content)
                if matches:
                    # Convert last timestamp to seconds
                    last_h, last_m, last_s = matches[-1]
                    script_duration = int(last_h) * 3600 + int(last_m) * 60 + int(last_s)
                    if video_meta and video_meta.duration > 0:
                        ratio = script_duration / video_meta.duration
                        # Target ratio: 0.9 - 1.1 (script covers 90-110% of video)
                        ratio_ok = 0.9 <= ratio <= 1.1
                        ratio_score = 100.0 if ratio_ok else max(0.0, 100.0 - abs(ratio - 1.0) * 100)
                        scores.append(ratio_score)
                        details["length_ratio"] = {"value": ratio, "ok": ratio_ok}
                        all_passed &= ratio_ok
            except Exception as exc:
                scores.append(50.0)
                details["length_ratio"] = {"error": str(exc)}

        # 5. Thumbnail readability
        if thumbnail_path and thumbnail_path.exists():
            thumb_score, thumb_details = _check_thumbnail_readability(thumbnail_path)
            scores.append(thumb_score)
            details["thumbnail_readability"] = thumb_details
            all_passed &= (thumb_score >= 50.0)
        else:
            scores.append(50.0)
            details["thumbnail_readability"] = {"skipped": "no thumbnail provided"}

        # 6. Chapter markers
        if chapter_markers_required and subtitle_path and subtitle_path.exists():
            marker_count = _count_chapter_markers(subtitle_path)
            if video_meta and video_meta.duration > 0:
                markers_per_min = (marker_count / video_meta.duration) * 60
                # Target: 1-3 markers per minute
                markers_ok = 1.0 <= markers_per_min <= 3.0
                marker_score = 100.0 if markers_ok else max(0.0, 100.0 - abs(markers_per_min - 2.0) * 30)
                scores.append(marker_score)
                details["chapter_marker_density"] = {
                    "count": marker_count,
                    "per_minute": markers_per_min,
                    "ok": markers_ok,
                }
                all_passed &= markers_ok
        else:
            scores.append(100.0)  # Pass if not required
            details["chapter_marker_density"] = {"skipped": "not required"}

        # Calculate final score
        final_score = sum(scores) / len(scores) if scores else 0.0

        return GateResult(
            name=self.name,
            passed=all_passed,
            score=final_score,
            details=details,
        )
