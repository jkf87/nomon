"""
Gnomon rubric module — eval-first harness.

Philosophy: rubric.yaml must exist before any workflow can run.
Like TDD (tests before code), Gnomon requires rubric before workflow.

Hierarchy:
  GoalPersona  — who the output is for
  Measure      — how to measure a single criterion
  RubricItem   — one evaluation criterion
  Rubric       — full eval contract for a workflow
  TasteGate    — meta-verifier: detect rubric drift vs human taste
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional


LabelEnum = Literal["quantitative", "persona-llm", "human"]
QUANTITATIVE_MIN_RATIO = 0.30  # block if quantitative < 30%


@dataclass
class GoalPersona:
    """Who the output is for, and what success looks like for them."""
    role: str
    success_signal: str


@dataclass
class Measure:
    """How to measure a single rubric criterion."""
    kind: str                       # e.g. clip_score, persona_judge, human_score
    gate: str                       # e.g. pass_if_gte, binary_pass, corr_gte
    threshold: Optional[float] = None
    persona_ref: Optional[str] = None   # reference key into goal_persona
    prompt_template: Optional[str] = None
    sample_n: Optional[int] = None
    scale: Optional[str] = None


@dataclass
class RubricItem:
    """A single evaluation criterion."""
    id: str
    name: str
    description: str
    label: LabelEnum
    pass_condition: str
    weight: float = 1.0
    measure: Optional[Measure] = field(default=None, repr=False)
    signal_fn: Optional[Callable] = field(default=None, repr=False)


@dataclass
class TasteGate:
    """Meta-verifier: tracks drift between human taste and LLM scoring."""
    trigger_every_n: int = 10
    spearman_threshold: float = 0.70
    drift_alert_drop: float = 0.15


@dataclass
class DryRunConfig:
    """Pre-flight checks before workflow entry."""
    require_quantitative_ratio: float = QUANTITATIVE_MIN_RATIO
    require_persona_ref_exists: bool = True
    require_signal_fn_callable: bool = False


@dataclass
class Rubric:
    """A complete eval contract for a Gnomon workflow."""
    task: str
    goal_persona: GoalPersona
    items: List[RubricItem] = field(default_factory=list)
    dry_run: DryRunConfig = field(default_factory=DryRunConfig)
    taste_gate: TasteGate = field(default_factory=TasteGate)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_rubric(path: Path) -> Rubric:
    """Load a rubric from a YAML file."""
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f)

    raw_persona = data.get("goal_persona") or data.get("persona")
    if isinstance(raw_persona, dict):
        persona = GoalPersona(
            role=raw_persona.get("role", ""),
            success_signal=raw_persona.get("success_signal", ""),
        )
    else:
        persona = GoalPersona(role=str(raw_persona or ""), success_signal="")

    items = []
    for raw in data.get("items", []):
        raw_measure = raw.get("measure")
        measure = None
        if isinstance(raw_measure, dict):
            measure = Measure(
                kind=raw_measure.get("kind", ""),
                gate=raw_measure.get("gate", ""),
                threshold=raw_measure.get("threshold"),
                persona_ref=raw_measure.get("persona_ref"),
                prompt_template=raw_measure.get("prompt_template"),
                sample_n=raw_measure.get("sample_n"),
                scale=raw_measure.get("scale"),
            )

        label = raw.get("label") or raw.get("method", "human")
        item = RubricItem(
            id=raw.get("id", raw.get("name", "")),
            name=raw.get("name", raw.get("id", "")),
            description=raw.get("description", ""),
            label=label,
            pass_condition=raw.get("pass_condition", ""),
            weight=float(raw.get("weight", 1.0)),
            measure=measure,
        )
        items.append(item)

    raw_dry = data.get("dry_run") or {}
    dry_run = DryRunConfig(
        require_quantitative_ratio=raw_dry.get("quantitative_ratio_min", QUANTITATIVE_MIN_RATIO),
        require_persona_ref_exists=raw_dry.get("require_persona_ref_exists", True),
        require_signal_fn_callable=raw_dry.get("require_signal_fn_callable", False),
    )

    raw_taste = data.get("taste_gate") or {}
    taste_gate = TasteGate(
        trigger_every_n=raw_taste.get("trigger_every_n", 10),
        spearman_threshold=raw_taste.get("spearman_threshold", 0.70),
        drift_alert_drop=raw_taste.get("drift_alert_drop", 0.15),
    )

    return Rubric(
        task=data.get("task", ""),
        goal_persona=persona,
        items=items,
        dry_run=dry_run,
        taste_gate=taste_gate,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class RubricValidationError(Exception):
    """Raised when rubric has a blocking issue (not just a warning)."""


def _label_counts(rubric: Rubric) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in rubric.items:
        counts[item.label] = counts.get(item.label, 0) + 1
    return counts


def validate_rubric(rubric: Rubric) -> List[str]:
    """Validate rubric. Returns list of warning strings.

    Raises RubricValidationError for blocking issues:
    - quantitative ratio < 30%
    - missing goal_persona.role

    Returns warnings (non-blocking):
    - empty items list
    - high persona-llm ratio (> 70%)
    """
    warnings_out: List[str] = []
    total = len(rubric.items)

    if total == 0:
        warnings_out.append("Rubric has no items defined.")
        return warnings_out

    counts = _label_counts(rubric)
    quant_count = counts.get("quantitative", 0)
    quant_ratio = quant_count / total

    if quant_ratio < QUANTITATIVE_MIN_RATIO:
        raise RubricValidationError(
            f"[BLOCK] quantitative items: {quant_count}/{total} ({quant_ratio:.0%}) "
            f"— minimum required: {QUANTITATIVE_MIN_RATIO:.0%}. "
            "Add quantitative signals to reduce LLM measurement bias."
        )

    if not rubric.goal_persona.role:
        raise RubricValidationError(
            "[BLOCK] goal_persona.role is required. "
            "Define who this output is for before running a workflow."
        )

    llm_count = counts.get("persona-llm", 0)
    llm_ratio = llm_count / total
    if llm_ratio >= 0.70:
        warnings_out.append(
            f"High persona-llm ratio: {llm_count}/{total} ({llm_ratio:.0%}). "
            "Consider adding more quantitative signals."
        )

    return warnings_out


def dry_run_check(rubric: Rubric) -> List[str]:
    """Pre-flight check before workflow entry. Returns list of error strings.

    Checks:
    1. All items have a label
    2. persona-llm items with persona_ref point to a non-empty goal_persona
    3. signal_fn is callable if require_signal_fn_callable is set
    """
    errors: List[str] = []

    for item in rubric.items:
        if not item.label:
            errors.append(f"Item '{item.id}': missing label (quantitative/persona-llm/human)")

        if item.label == "persona-llm" and item.measure and item.measure.persona_ref:
            if not rubric.goal_persona.role:
                errors.append(
                    f"Item '{item.id}': persona_ref set but goal_persona.role is empty"
                )

        if rubric.dry_run.require_signal_fn_callable and item.label == "quantitative":
            if item.signal_fn is not None and not callable(item.signal_fn):
                errors.append(f"Item '{item.id}': signal_fn is not callable")

    return errors
