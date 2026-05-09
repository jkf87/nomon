"""Tests for the rubric engine."""

import pytest
import yaml
from pathlib import Path

from openclaw_gnomon.rubric_engine import (
    Rubric, Criterion, Measure, Label, TaskDef, GoalPersona,
    load_rubric, dry_run,
)


@pytest.fixture
def valid_rubric_yaml(tmp_path):
    data = {
        "task": {
            "name": "test task",
            "description": "test desc",
            "goal_persona": {"role": "25~35 직장인", "success_signal": "5초 요약 가능"},
        },
        "rubric": [
            {
                "id": "r1",
                "description": "이미지 일치",
                "label": "quantitative",
                "measure": {"kind": "clip_score", "threshold": 0.25, "gate": "pass_if_gte"},
                "weight": 1.0,
            },
            {
                "id": "r2",
                "description": "핵심 전달력",
                "label": "persona-llm",
                "measure": {
                    "kind": "persona_judge",
                    "persona_ref": "25~35 직장인",
                    "prompt_template": "요약 가능? PASS/FAIL",
                    "gate": "binary_pass",
                },
                "weight": 0.7,
            },
            {
                "id": "r3",
                "description": "종합 만족도",
                "label": "human",
                "measure": {"kind": "human_score", "sample_n": 5, "scale": "0..5", "gate": "corr_with_llm_pool_gte_0_7"},
                "weight": 1.5,
            },
        ],
    }
    p = tmp_path / "rubric.yaml"
    with open(p, "w") as f:
        yaml.dump(data, f)
    return p


def test_load_rubric(valid_rubric_yaml):
    rubric = load_rubric(valid_rubric_yaml)
    assert rubric.task.name == "test task"
    assert len(rubric.rubric) == 3


def test_quantitative_ratio(valid_rubric_yaml):
    rubric = load_rubric(valid_rubric_yaml)
    ratio = rubric.quantitative_ratio()
    assert ratio >= 0.3  # 1/3 ≈ 0.33


def test_label_counts(valid_rubric_yaml):
    rubric = load_rubric(valid_rubric_yaml)
    counts = rubric.label_counts()
    assert counts["quantitative"] == 1
    assert counts["persona-llm"] == 1
    assert counts["human"] == 1


def test_dry_run_pass(valid_rubric_yaml):
    rubric = load_rubric(valid_rubric_yaml)
    report = dry_run(rubric)
    assert report["status"] == "pass"


def test_dry_run_unknown_kind(tmp_path):
    data = {
        "task": {
            "name": "t",
            "description": "d",
            "goal_persona": {"role": "r", "success_signal": "s"},
        },
        "rubric": [
            {
                "id": "r1",
                "description": "test",
                "label": "quantitative",
                "measure": {"kind": "nonexistent_thing", "threshold": 0.5, "gate": "pass_if_gte"},
            },
        ],
    }
    p = tmp_path / "rubric.yaml"
    with open(p, "w") as f:
        yaml.dump(data, f)
    rubric = load_rubric(p)
    report = dry_run(rubric)
    assert report["status"] == "fail"
    assert any("unknown measure.kind" in i for c in report["criteria"] for i in c.get("issues", []))


def test_reject_llm_only(tmp_path):
    """All persona-llm and no quantitative should fail validation."""
    data = {
        "task": {
            "name": "t",
            "description": "d",
            "goal_persona": {"role": "r", "success_signal": "s"},
        },
        "rubric": [
            {
                "id": "r1",
                "description": "test",
                "label": "persona-llm",
                "measure": {"kind": "persona_judge", "persona_ref": "r", "prompt_template": "ok?", "gate": "binary_pass"},
            },
            {
                "id": "r2",
                "description": "test2",
                "label": "persona-llm",
                "measure": {"kind": "persona_judge", "persona_ref": "r", "prompt_template": "ok?", "gate": "binary_pass"},
            },
        ],
    }
    p = tmp_path / "rubric.yaml"
    with open(p, "w") as f:
        yaml.dump(data, f)
    with pytest.raises(Exception):
        load_rubric(p)
