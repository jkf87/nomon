"""Tests for nomon rubric module — eval-first harness."""
import pytest
from pathlib import Path

from openclaw_gnomon.rubric import (
    QUANTITATIVE_MIN_RATIO,
    DryRunConfig,
    GoalPersona,
    Measure,
    Rubric,
    RubricItem,
    RubricValidationError,
    TasteGate,
    dry_run_check,
    load_rubric,
    validate_rubric,
)


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------

def test_goal_persona_creation():
    p = GoalPersona(role="25~35세 직장인", success_signal="5초 요약 가능")
    assert p.role == "25~35세 직장인"
    assert p.success_signal == "5초 요약 가능"


def test_rubric_item_creation():
    item = RubricItem(
        id="r1",
        name="font size check",
        description="All text >= 24pt",
        label="quantitative",
        pass_condition="font_size >= 24",
    )
    assert item.name == "font size check"
    assert item.label == "quantitative"
    assert item.signal_fn is None
    assert item.weight == 1.0


def test_rubric_item_with_signal_fn():
    def my_signal():
        return True

    item = RubricItem(
        id="r-sig",
        name="custom check",
        description="Custom signal",
        label="quantitative",
        pass_condition="returns True",
        signal_fn=my_signal,
    )
    assert item.signal_fn is my_signal
    assert item.signal_fn() is True


def test_rubric_creation():
    rubric = Rubric(
        task="Generate card news",
        goal_persona=GoalPersona(role="office worker", success_signal="5s summary"),
        items=[],
    )
    assert rubric.task == "Generate card news"
    assert rubric.items == []
    assert isinstance(rubric.taste_gate, TasteGate)
    assert isinstance(rubric.dry_run, DryRunConfig)


def test_taste_gate_defaults():
    tg = TasteGate()
    assert tg.spearman_threshold == 0.70
    assert tg.drift_alert_drop == 0.15
    assert tg.trigger_every_n == 10


# ---------------------------------------------------------------------------
# validate_rubric — blocking errors
# ---------------------------------------------------------------------------

def test_validate_rubric_blocks_when_quantitative_below_30pct():
    """validate_rubric raises RubricValidationError when quantitative < 30%."""
    items = [
        RubricItem(id=f"llm-{i}", name=f"llm-{i}", description="", label="persona-llm", pass_condition="")
        for i in range(3)
    ]
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="tester", success_signal=""),
        items=items,
    )
    with pytest.raises(RubricValidationError, match="BLOCK"):
        validate_rubric(rubric)


def test_validate_rubric_blocks_missing_goal_persona_role():
    """validate_rubric raises RubricValidationError when goal_persona.role is empty."""
    items = [
        RubricItem(id="q1", name="q1", description="", label="quantitative", pass_condition=""),
        RubricItem(id="q2", name="q2", description="", label="quantitative", pass_condition=""),
        RubricItem(id="h1", name="h1", description="", label="human", pass_condition=""),
    ]
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="", success_signal=""),
        items=items,
    )
    with pytest.raises(RubricValidationError, match="goal_persona"):
        validate_rubric(rubric)


def test_validate_rubric_passes_with_30pct_quantitative():
    """validate_rubric passes when quantitative >= 30%."""
    items = [
        RubricItem(id="q1", name="q1", description="", label="quantitative", pass_condition=""),
        RubricItem(id="llm1", name="llm1", description="", label="persona-llm", pass_condition=""),
        RubricItem(id="h1", name="h1", description="", label="human", pass_condition=""),
    ]
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="tester", success_signal=""),
        items=items,
    )
    warnings = validate_rubric(rubric)
    assert warnings == []


def test_validate_rubric_warns_high_llm_ratio():
    """validate_rubric warns when persona-llm ratio > 70% (while quantitative >= 30%)."""
    # 3 quantitative (30%) + 7 persona-llm (70%) = 10 items
    # quantitative passes the 30% gate; persona-llm at exactly 70% triggers warning
    items = (
        [RubricItem(id=f"q{i}", name=f"q{i}", description="", label="quantitative", pass_condition="")
         for i in range(3)]
        + [RubricItem(id=f"llm{i}", name=f"llm{i}", description="", label="persona-llm", pass_condition="")
           for i in range(7)]
    )
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="tester", success_signal=""),
        items=items,
    )
    warnings = validate_rubric(rubric)
    assert any("persona-llm" in w for w in warnings)


def test_validate_rubric_empty_items_returns_warning():
    """validate_rubric returns a warning (not an error) for empty items."""
    rubric = Rubric(
        task="Empty task",
        goal_persona=GoalPersona(role="tester", success_signal=""),
        items=[],
    )
    warnings = validate_rubric(rubric)
    assert any("no items" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# dry_run_check
# ---------------------------------------------------------------------------

def test_dry_run_check_passes_valid_rubric():
    items = [
        RubricItem(id="q1", name="q1", description="", label="quantitative", pass_condition=""),
        RubricItem(id="h1", name="h1", description="", label="human", pass_condition=""),
    ]
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="tester", success_signal=""),
        items=items,
    )
    errors = dry_run_check(rubric)
    assert errors == []


def test_dry_run_check_detects_missing_persona_role_for_persona_llm():
    measure = Measure(kind="persona_judge", gate="binary_pass", persona_ref="goal_persona.role")
    items = [
        RubricItem(id="q1", name="q1", description="", label="quantitative", pass_condition=""),
        RubricItem(id="llm1", name="llm1", description="", label="persona-llm",
                   pass_condition="", measure=measure),
    ]
    rubric = Rubric(
        task="Test",
        goal_persona=GoalPersona(role="", success_signal=""),
        items=items,
    )
    errors = dry_run_check(rubric)
    assert any("goal_persona.role is empty" in e for e in errors)


# ---------------------------------------------------------------------------
# load_rubric from YAML
# ---------------------------------------------------------------------------

def test_load_rubric_from_yaml_new_schema(tmp_path):
    """load_rubric parses goal_persona dict and label field."""
    yaml_content = """
task: "Test workflow"
goal_persona:
  role: "Dev tester"
  success_signal: "passes CI"
items:
  - id: r1
    name: "Output exists"
    description: "File is created"
    label: quantitative
    pass_condition: "file exists"
    weight: 1.0
  - id: r2
    name: "Quality check"
    description: "LLM review"
    label: persona-llm
    pass_condition: "score >= 7"
    weight: 0.7
    measure:
      kind: persona_judge
      gate: binary_pass
      persona_ref: goal_persona.role
taste_gate:
  trigger_every_n: 5
  spearman_threshold: 0.75
"""
    rubric_file = tmp_path / "rubric.yaml"
    rubric_file.write_text(yaml_content)

    rubric = load_rubric(rubric_file)
    assert rubric.task == "Test workflow"
    assert rubric.goal_persona.role == "Dev tester"
    assert rubric.goal_persona.success_signal == "passes CI"
    assert len(rubric.items) == 2
    assert rubric.items[0].label == "quantitative"
    assert rubric.items[1].label == "persona-llm"
    assert rubric.items[1].measure is not None
    assert rubric.items[1].measure.persona_ref == "goal_persona.role"
    assert rubric.taste_gate.trigger_every_n == 5
    assert rubric.taste_gate.spearman_threshold == 0.75


def test_load_rubric_backwards_compat_persona_string(tmp_path):
    """load_rubric handles legacy 'persona: string' format."""
    yaml_content = """
task: "Legacy rubric"
persona: "25~35세 직장인"
items:
  - id: r1
    name: "check"
    description: ""
    method: quantitative
    pass_condition: "ok"
"""
    rubric_file = tmp_path / "rubric.yaml"
    rubric_file.write_text(yaml_content)

    rubric = load_rubric(rubric_file)
    assert rubric.goal_persona.role == "25~35세 직장인"
