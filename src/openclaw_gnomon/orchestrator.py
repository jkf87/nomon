"""
GnomonOrchestrator — main pipeline tying loaders, spawners, gates, and reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openclaw_gnomon.gates import gate_for
from openclaw_gnomon.gates.base import GateResult
from openclaw_gnomon.report import AgentEvaluation, EvaluationReport, build_report
from openclaw_gnomon.spawner import AgentSpawner, SpawnResult
from openclaw_gnomon.task_schema import GnomonTask, load_task


class GnomonOrchestrator:
    """Run the full evaluation pipeline."""

    def __init__(
        self,
        spawner: Optional[AgentSpawner] = None,
        runs_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self.spawner = spawner or AgentSpawner(dry_run=dry_run)
        self.runs_dir = Path(runs_dir) if runs_dir else Path(".nomon/runs")
        self.dry_run = dry_run

    # ------------------------------------------------------------------

    def run_from_path(self, task_path: Path) -> EvaluationReport:
        task = load_task(Path(task_path))
        return self.run(task)

    def run(self, task: GnomonTask) -> EvaluationReport:
        run_dir = self._make_run_dir(task)
        agents_dir = run_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        spawn_results = self.spawner.spawn_all(task, agents_dir)

        spec = task.parsed_spec()
        gate = gate_for(task.task_type)

        evaluations = []
        for agent_name, spawn in spawn_results.items():
            gate_results, notes = self._evaluate_agent(spawn, gate, spec)
            total = self._weighted_total(gate_results)
            evaluations.append(
                AgentEvaluation(
                    agent_name=agent_name,
                    gate_results=gate_results,
                    total_score=total,
                    duration_seconds=spawn.duration_seconds,
                    notes=notes,
                    skipped=spawn.skipped,
                )
            )

        report = build_report(task.name, task.task_type, evaluations)
        self._persist_report(run_dir, report)
        return report

    # ------------------------------------------------------------------

    def _evaluate_agent(self, spawn: SpawnResult, gate, spec):
        notes = []
        if spawn.note:
            notes.append(spawn.note)
        if spawn.exit_code != 0 and not spawn.skipped:
            notes.append(f"agent exit code: {spawn.exit_code}")

        if spawn.skipped:
            return [
                GateResult(
                    name=gate.name,
                    passed=False,
                    score=0.0,
                    details={"reason": "agent skipped — gate not run"},
                )
            ], notes

        try:
            result = gate.evaluate(spawn.output_dir, spec)
        except Exception as exc:  # noqa: BLE001 — surface gate errors to user
            result = GateResult(
                name=gate.name,
                passed=False,
                score=0.0,
                details={"error": f"gate raised {type(exc).__name__}: {exc}"},
            )
        return [result], notes

    @staticmethod
    def _weighted_total(gate_results) -> float:
        if not gate_results:
            return 0.0
        return sum(g.score for g in gate_results) / len(gate_results)

    def _make_run_dir(self, task: GnomonTask) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = "".join(c if c.isalnum() else "-" for c in task.name).strip("-").lower() or "task"
        run_dir = self.runs_dir / f"{ts}-{slug}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    @staticmethod
    def _persist_report(run_dir: Path, report: EvaluationReport) -> None:
        (run_dir / "report.json").write_text(report.to_json(), encoding="utf-8")
        (run_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
