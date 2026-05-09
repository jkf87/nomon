"""Tests for the orchestrator end-to-end pipeline."""
from pathlib import Path

import yaml

from openclaw_gnomon.orchestrator import GnomonOrchestrator
from openclaw_gnomon.spawner import AgentSpawner, SpawnResult
from openclaw_gnomon.task_schema import GnomonTask, load_task


class _FakeSpawner(AgentSpawner):
    """Fake spawner that drops a deterministic file into each agent dir."""

    def __init__(self, content_per_agent):
        super().__init__(dry_run=True)
        self._content = content_per_agent

    def spawn_all(self, task, base_dir):
        results = {}
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        for agent in task.agents:
            agent_dir = base_dir / agent
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "out.md").write_text(
                self._content.get(agent, "default"),
                encoding="utf-8",
            )
            results[agent] = SpawnResult(
                agent=agent,
                output_dir=agent_dir,
                exit_code=0,
                duration_seconds=0.1,
                skipped=False,
            )
        return results


def test_orchestrator_runs_and_ranks_agents(tmp_path):
    task_data = {
        "name": "Translate test",
        "task_type": "translation",
        "spec": {
            "source_path": str(tmp_path / "source.md"),
            "target_lang": "ko",
            "proper_nouns": ["Anthropic"],
        },
        "agents": ["claude-code", "codex"],
    }
    (tmp_path / "source.md").write_text(
        "Anthropic builds Claude. Anthropic is in San Francisco.",
        encoding="utf-8",
    )

    task_path = tmp_path / "task.yaml"
    task_path.write_text(yaml.safe_dump(task_data), encoding="utf-8")
    task = load_task(task_path)

    spawner = _FakeSpawner(
        content_per_agent={
            "claude-code": "Anthropic이 Claude를 만든다. Anthropic은 SF에 있다.",
            "codex": "그 회사가 그것을 만든다.",
        }
    )
    orch = GnomonOrchestrator(spawner=spawner, runs_dir=tmp_path / "runs")
    report = orch.run(task)

    assert report.task_name == "Translate test"
    assert report.task_type == "translation"
    assert {a.agent_name for a in report.agents} == {"claude-code", "codex"}
    claude = next(a for a in report.agents if a.agent_name == "claude-code")
    codex = next(a for a in report.agents if a.agent_name == "codex")
    assert claude.total_score >= codex.total_score
    assert report.winner == claude.agent_name

    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "report.json").exists()
    assert (runs[0] / "report.md").exists()


def test_orchestrator_handles_skipped_agent(tmp_path):
    task = GnomonTask(
        name="Skipped",
        task_type="code",
        spec={"prompt": "x"},
        agents=["claude-code"],
    )

    class _SkipSpawner(AgentSpawner):
        def __init__(self):
            super().__init__(dry_run=True)

        def spawn_all(self, task, base_dir):
            agent_dir = Path(base_dir) / "claude-code"
            agent_dir.mkdir(parents=True, exist_ok=True)
            return {
                "claude-code": SpawnResult(
                    agent="claude-code",
                    output_dir=agent_dir,
                    exit_code=127,
                    duration_seconds=0.0,
                    skipped=True,
                    note="binary missing",
                )
            }

    orch = GnomonOrchestrator(spawner=_SkipSpawner(), runs_dir=tmp_path / "runs")
    report = orch.run(task)
    assert report.agents[0].skipped is True
    assert report.winner is None
