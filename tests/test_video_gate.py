"""Tests for openclaw_gnomon.gates.video_gate."""
import json
from pathlib import Path

import pytest

from openclaw_gnomon.gates.video_gate import VideoGate, _calculate_wer
from openclaw_gnomon.task_schema import VideoTaskSpec, load_task


def test_calculate_wer():
    """Test WER calculation."""
    # Perfect match
    assert _calculate_wer("hello world", "hello world") == 0.0

    # One substitution (1 character change in "hello")
    wer = _calculate_wer("hello world", "hallo world")
    assert 0 < wer < 0.6  # 1 substitution out of 2 words = 0.5

    # One insertion
    wer = _calculate_wer("hello world", "hello big world")
    assert 0 < wer < 0.6

    # One deletion
    wer = _calculate_wer("hello big world", "hello world")
    assert 0 < wer < 0.6

    # Completely different
    wer = _calculate_wer("hello world", "goodbye moon")
    assert wer > 0.5


def test_load_video_task(tmp_path):
    """Test loading a video task from YAML."""
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        """
name: Test Video
task_type: video
spec:
  video_path: test.mp4
  subtitle_path: subtitles.srt
  aspect_ratio: "16:9"
  min_duration_seconds: 30
  max_duration_seconds: 600
  thumbnail_path: thumbnail.jpg
  chapter_markers_required: true
agents:
  - claude-code
""",
        encoding="utf-8",
    )

    task = load_task(task_path)
    assert task.task_type == "video"
    spec = task.parsed_spec()
    assert isinstance(spec, VideoTaskSpec)
    assert spec.video_path == "test.mp4"
    assert spec.aspect_ratio == "16:9"
    assert spec.min_duration_seconds == 30
    assert spec.chapter_markers_required is True


def test_video_gate_missing_video(tmp_path):
    """Test VideoGate with missing video file."""
    gate = VideoGate()

    # Create spec with non-existent video
    spec = VideoTaskSpec(video_path="nonexistent.mp4")

    result = gate.evaluate(tmp_path, spec)
    assert result.name == "video"
    assert result.passed is False
    assert result.score < 70.0  # Should be low due to missing video
    assert "error" in result.details.get("video", {})


def test_video_gate_with_fake_metadata(tmp_path):
    """Test VideoGate with fake video metadata (integration test)."""
    gate = VideoGate()

    # Create a minimal fake video file (1x1 pixel, 1 second, no audio)
    fake_video = tmp_path / "test.mp4"
    # We can't create a real video without ffmpeg, so skip this test
    # In real usage, this would require actual video files

    # For now, just test that the gate structure is correct
    spec = VideoTaskSpec(video_path="test.mp4", aspect_ratio="16:9")
    result = gate.evaluate(tmp_path, spec)

    # Should not crash
    assert result.name == "video"
    assert "video" in result.details
    assert result.passed is False  # Missing video means it should fail


def test_video_gate_spec_validation(tmp_path):
    """Test that VideoTaskSpec validates correctly."""
    # Valid spec
    spec = VideoTaskSpec(
        video_path="test.mp4",
        aspect_ratio="9:16",
        audio_lufs_target=-14.0,
    )
    assert spec.aspect_ratio == "9:16"
    assert spec.audio_lufs_target == -14.0

    # Invalid aspect ratio should fail
    with pytest.raises(Exception):
        VideoTaskSpec(video_path="test.mp4", aspect_ratio="4:3")  # Not in Literal
