"""Tests for openclaw_gnomon.spawner."""
from pathlib import Path

from openclaw_gnomon.spawner import AgentSpawner, _build_prompt
from openclaw_gnomon.task_schema import GnomonTask


def test_build_prompt_uses_spec_prompt():
    task = GnomonTask(
        name="t",
        task_type="code",
        spec={"prompt": "do X"},
        agents=["claude-code"],
    )
    assert "do X" in _build_prompt(task)


def test_build_prompt_appends_context_for_translation():
    task = GnomonTask(
        name="t",
        task_type="translation",
        spec={
            "prompt": "translate",
            "source_path": "docs/",
            "target_lang": "ko",
        },
        agents=["claude-code"],
    )
    rendered = _build_prompt(task)
    assert "translate" in rendered
    assert "source_path: docs/" in rendered
    assert "target_lang: ko" in rendered


def test_dry_run_writes_placeholder_files(tmp_path):
    task = GnomonTask(
        name="t",
        task_type="code",
        spec={"prompt": "do something"},
        agents=["claude-code", "codex"],
    )
    spawner = AgentSpawner(dry_run=True)
    results = spawner.spawn_all(task, tmp_path)
    assert set(results.keys()) == {"claude-code", "codex"}
    for agent, result in results.items():
        assert result.skipped is True
        assert result.exit_code == 0
        assert (Path(result.output_dir) / "DRY_RUN.txt").exists()


def test_unsupported_agent_is_skipped(tmp_path):
    # Bypass pydantic Literal validation — this test checks that the spawner
    # handles agents it doesn't know how to spawn.
    task = GnomonTask(
        name="t",
        task_type="code",
        spec={"prompt": "x"},
        agents=["claude-code"],
    )
    # Manually inject an unsupported agent name
    task.agents = ["mystery-agent"]  # type: ignore[list-item]
    spawner = AgentSpawner(dry_run=False)
    results = spawner.spawn_all(task, tmp_path)
    res = results["mystery-agent"]
    assert res.skipped is True
    assert res.exit_code == 2


def test_missing_binary_is_handled(tmp_path):
    task = GnomonTask(
        name="t",
        task_type="code",
        spec={"prompt": "x"},
        agents=["claude-code"],
    )
    spawner = AgentSpawner(
        claude_bin="this-binary-does-not-exist-claude-xyz",
        codex_bin="this-binary-does-not-exist-codex-xyz",
        dry_run=False,
    )
    results = spawner.spawn_all(task, tmp_path)
    assert results["claude-code"].skipped is True
    assert results["claude-code"].exit_code == 127
