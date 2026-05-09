"""Rubric engine — parse, validate, and dry-run rubric YAML files."""

import json
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class Label(str, Enum):
    QUANTITATIVE = "quantitative"
    PERSONA_LLM = "persona-llm"
    HUMAN = "human"


class Measure(BaseModel):
    kind: str
    threshold: float | None = None
    gate: str = "pass_if_gte"
    persona_ref: str | None = None
    prompt_template: str | None = None
    sample_n: int | None = None
    scale: str | None = None


class Criterion(BaseModel):
    id: str
    description: str
    label: Label
    measure: Measure
    weight: float = 1.0


class GoalPersona(BaseModel):
    role: str
    success_signal: str


class TaskDef(BaseModel):
    name: str
    description: str
    goal_persona: GoalPersona


class Rubric(BaseModel):
    task: TaskDef
    rubric: list[Criterion]

    @field_validator("rubric")
    @classmethod
    def validate_quantitative_ratio(cls, v: list[Criterion]) -> list[Criterion]:
        if not v:
            raise ValueError("rubric must have at least one criterion")
        quant_count = sum(1 for c in v if c.label == Label.QUANTITATIVE)
        ratio = quant_count / len(v)
        if ratio < 0.3:
            raise ValueError(
                f"quantitative ratio {ratio:.0%} is below minimum 30%. "
                f"Add more quantitative criteria."
            )
        return v

    @field_validator("rubric")
    @classmethod
    def validate_labels_present(cls, v: list[Criterion]) -> list[Criterion]:
        for c in v:
            if c.label == Label.PERSONA_LLM and not c.measure.persona_ref:
                raise ValueError(
                    f"criterion {c.id}: persona-llm label requires measure.persona_ref"
                )
            if c.label == Label.HUMAN and (not c.measure.sample_n or c.measure.sample_n < 3):
                raise ValueError(
                    f"criterion {c.id}: human label requires measure.sample_n >= 3"
                )
        return v

    def quantitative_ratio(self) -> float:
        return sum(1 for c in self.rubric if c.label == Label.QUANTITATIVE) / len(self.rubric)

    def label_counts(self) -> dict[str, int]:
        counts = {"quantitative": 0, "persona-llm": 0, "human": 0}
        for c in self.rubric:
            counts[c.label.value] += 1
        return counts


def load_rubric(path: Path) -> Rubric:
    """Load and validate a rubric YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return Rubric(**data)


def dry_run(rubric: Rubric) -> dict[str, Any]:
    """Check if rubric criteria can actually produce PASS/FAIL.

    Returns a report with status and details.
    """
    results = []
    all_pass = True

    for c in rubric.rubric:
        detail = {"id": c.id, "label": c.label.value, "status": "ok", "issues": []}

        if c.label == Label.QUANTITATIVE:
            # Check that kind is a known callable
            known_kinds = {
                "clip_score", "test_exit_code", "type_check", "lint",
                "build_success", "wcag_contrast", "font_size", "char_count",
                "image_count", "resolution", "link_liveness", "spell_check",
                "image_alt", "screenshot_diff", "dom_snapshot",
                "comet_score", "bleu_score", "length_ratio", "ner_preservation",
            }
            if c.measure.kind not in known_kinds:
                detail["issues"].append(f"unknown measure.kind: {c.measure.kind}")
                detail["status"] = "fail"
                all_pass = False
            if c.measure.threshold is None and c.measure.gate != "binary_pass":
                detail["issues"].append("quantitative criterion needs threshold")
                detail["status"] = "warn"

        elif c.label == Label.PERSONA_LLM:
            if not c.measure.persona_ref:
                detail["issues"].append("persona_ref missing")
                detail["status"] = "fail"
                all_pass = False
            if not c.measure.prompt_template:
                detail["issues"].append("prompt_template missing")
                detail["status"] = "fail"
                all_pass = False

        elif c.label == Label.HUMAN:
            if not c.measure.sample_n or c.measure.sample_n < 3:
                detail["issues"].append("sample_n must be >= 3")
                detail["status"] = "fail"
                all_pass = False

        results.append(detail)

    report = {
        "status": "pass" if all_pass else "fail",
        "quantitative_ratio": rubric.quantitative_ratio(),
        "label_counts": rubric.label_counts(),
        "criteria": results,
        "action": "proceed" if all_pass else "fix_issues_before_workflow",
    }

    if all_pass and rubric.quantitative_ratio() < 0.3:
        report["status"] = "fail"
        report["action"] = "increase_quantitative_criteria"

    return report
