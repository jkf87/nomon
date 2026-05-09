"""Tests for openclaw_gnomon.report."""
import json

from openclaw_gnomon.gates.base import GateResult
from openclaw_gnomon.report import AgentEvaluation, build_report


def _make_eval(name, score, skipped=False):
    return AgentEvaluation(
        agent_name=name,
        gate_results=[
            GateResult(name="dummy", passed=score >= 70, score=score, details={"k": "v"})
        ],
        total_score=score,
        duration_seconds=1.5,
        skipped=skipped,
    )


def test_build_report_ranks_by_score():
    report = build_report(
        task_name="t",
        task_type="code",
        agent_evals=[_make_eval("a", 50.0), _make_eval("b", 90.0)],
    )
    assert report.agents[0].agent_name == "b"
    assert report.agents[0].rank == 1
    assert report.agents[1].rank == 2
    assert report.winner == "b"


def test_build_report_skips_skipped_agents_for_winner():
    report = build_report(
        task_name="t",
        task_type="ui",
        agent_evals=[_make_eval("a", 99.0, skipped=True), _make_eval("b", 60.0)],
    )
    assert report.winner == "b"


def test_to_json_round_trip():
    report = build_report(
        task_name="t",
        task_type="blog",
        agent_evals=[_make_eval("a", 70.0)],
    )
    payload = json.loads(report.to_json())
    assert payload["task_name"] == "t"
    assert payload["agents"][0]["gate_results"][0]["score"] == 70.0


def test_to_markdown_includes_ranking():
    report = build_report(
        task_name="task-X",
        task_type="translation",
        agent_evals=[_make_eval("alpha", 80.0), _make_eval("beta", 40.0)],
    )
    md = report.to_markdown()
    assert "Gnomon Evaluation Report — task-X" in md
    assert "alpha" in md
    assert "beta" in md
    assert "Ranking" in md
