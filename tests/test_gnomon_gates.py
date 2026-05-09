"""Tests for the gates package (code/translation/blog/ui)."""
import pytest

from openclaw_gnomon.gates import gate_for
from openclaw_gnomon.gates.base import GateResult
from openclaw_gnomon.gates.translation_gate import simple_bleu
from openclaw_gnomon.task_schema import (
    BlogTaskSpec,
    CodeTaskSpec,
    TranslationTaskSpec,
    UITaskSpec,
)


# ---------------------------------------------------------------------------
# Code gate
# ---------------------------------------------------------------------------

def test_code_gate_no_commands_fails(tmp_path):
    gate = gate_for("code")
    spec = CodeTaskSpec(prompt="x")
    result = gate.evaluate(tmp_path, spec)
    assert isinstance(result, GateResult)
    assert result.passed is False
    assert result.score == 0.0


def test_code_gate_runs_passing_command(tmp_path):
    gate = gate_for("code")
    spec = CodeTaskSpec(prompt="x", test_command="python3 -c 'pass'")
    result = gate.evaluate(tmp_path, spec)
    assert result.passed is True
    assert result.score == 100.0


def test_code_gate_runs_failing_command(tmp_path):
    gate = gate_for("code")
    spec = CodeTaskSpec(prompt="x", test_command="python3 -c 'raise SystemExit(1)'")
    result = gate.evaluate(tmp_path, spec)
    assert result.passed is False
    assert result.score == 0.0


def test_code_gate_unknown_binary_does_not_count(tmp_path):
    gate = gate_for("code")
    spec = CodeTaskSpec(prompt="x", test_command="this-binary-does-not-exist-xyz")
    result = gate.evaluate(tmp_path, spec)
    assert result.passed is False
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# Translation gate
# ---------------------------------------------------------------------------

def test_simple_bleu_self_match():
    text = "the quick brown fox jumps over the lazy dog"
    score = simple_bleu(text, text)
    assert score > 0.9


def test_simple_bleu_no_match():
    score = simple_bleu("alpha beta gamma", "completely unrelated words here")
    assert score < 0.1


def test_translation_gate_proper_noun_preservation(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("Claude was made by Anthropic." * 5, encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    (out / "ko.md").write_text(
        ("Claude는 Anthropic이 만들었습니다." * 5),
        encoding="utf-8",
    )

    spec = TranslationTaskSpec(
        source_path=str(src),
        target_lang="ko",
        proper_nouns=["Claude", "Anthropic"],
    )
    gate = gate_for("translation")
    result = gate.evaluate(out, spec)
    assert result.details["proper_nouns"]["missing"] == []


def test_translation_gate_flags_missing_proper_noun(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("Claude is from Anthropic.", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "ko.md").write_text("It is from somewhere.", encoding="utf-8")

    spec = TranslationTaskSpec(
        source_path=str(src),
        target_lang="ko",
        proper_nouns=["Claude", "Anthropic"],
    )
    gate = gate_for("translation")
    result = gate.evaluate(out, spec)
    assert "Claude" in result.details["proper_nouns"]["missing"]
    assert "Anthropic" in result.details["proper_nouns"]["missing"]


# ---------------------------------------------------------------------------
# Blog gate
# ---------------------------------------------------------------------------

def test_blog_gate_no_files(tmp_path):
    gate = gate_for("blog")
    spec = BlogTaskSpec(content_path="missing")
    result = gate.evaluate(tmp_path, spec)
    assert result.passed is False


def test_blog_gate_html_with_alt(tmp_path):
    out = tmp_path / "blog"
    out.mkdir()
    (out / "post.html").write_text(
        "<html><body><img src='a.png' alt='ok'></body></html>",
        encoding="utf-8",
    )
    spec = BlogTaskSpec(content_path=str(out), check_links=False)
    gate = gate_for("blog")
    result = gate.evaluate(out, spec)
    assert result.details["image_alt"]["passed"] is True


def test_blog_gate_html_missing_alt(tmp_path):
    out = tmp_path / "blog"
    out.mkdir()
    (out / "post.html").write_text(
        "<html><body><img src='a.png'></body></html>",
        encoding="utf-8",
    )
    spec = BlogTaskSpec(content_path=str(out), check_links=False)
    gate = gate_for("blog")
    result = gate.evaluate(out, spec)
    assert result.details["image_alt"]["passed"] is False


# ---------------------------------------------------------------------------
# UI gate
# ---------------------------------------------------------------------------

def test_ui_gate_passing_contrast(tmp_path):
    out = tmp_path / "ui"
    out.mkdir()
    (out / "index.html").write_text(
        "<html><body style=\"color:#000000;background:#ffffff\">"
        "<img src='a.png' alt='ok'>Hello</body></html>",
        encoding="utf-8",
    )
    spec = UITaskSpec(html_path="index.html", wcag_level="AA")
    gate = gate_for("ui")
    result = gate.evaluate(out, spec)
    assert result.details["wcag"]["passed_pairs"] == 1
    assert result.details["image_alt"]["passed"] is True


def test_ui_gate_failing_contrast(tmp_path):
    out = tmp_path / "ui"
    out.mkdir()
    (out / "index.html").write_text(
        "<html><body style=\"color:#aaaaaa;background:#bbbbbb\">"
        "<p>Hi</p></body></html>",
        encoding="utf-8",
    )
    spec = UITaskSpec(html_path="index.html", wcag_level="AAA")
    gate = gate_for("ui")
    result = gate.evaluate(out, spec)
    assert result.details["wcag"]["passed_pairs"] == 0


def test_gate_for_unknown_type_raises():
    with pytest.raises(ValueError):
        gate_for("nope")
