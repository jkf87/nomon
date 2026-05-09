"""
AgentSpawner — runs Claude Code and Codex as competing agents and collects
their outputs into per-agent directories.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from openclaw_nomon.task_schema import NomonTask


@dataclass
class SpawnResult:
    agent: str
    output_dir: Path
    exit_code: int
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    note: str = ""


def _build_prompt(task: NomonTask) -> str:
    """Render a unified prompt the agent receives, regardless of task_type."""
    spec = task.parsed_spec()
    base = getattr(spec, "prompt", None) or f"Complete the {task.task_type} task '{task.name}'."
    extras: List[str] = []
    for field_name in (
        "source_path",
        "target_lang",
        "content_path",
        "url",
        "html_path",
    ):
        value = getattr(spec, field_name, None)
        if value:
            extras.append(f"{field_name}: {value}")
    if extras:
        base = base + "\n\nContext:\n" + "\n".join(f"- {e}" for e in extras)
    return base


def _resolve_working_dir(task: NomonTask, base_dir: Path) -> Path:
    spec = task.parsed_spec()
    candidate = getattr(spec, "working_dir", None)
    if not candidate:
        return base_dir
    p = Path(candidate)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


async def _run_subprocess(
    argv: List[str],
    cwd: Path,
    timeout: int,
    env: Optional[Dict[str, str]] = None,
    stdin_data: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.monotonic()
    full_env = {**os.environ, **(env or {})}
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(stdin_data.encode("utf-8") if stdin_data else None),
            timeout=timeout,
        )
        exit_code = proc.returncode if proc.returncode is not None else -1
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "exit_code": 124,
            "duration": time.monotonic() - started,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
        }
    return {
        "exit_code": exit_code,
        "duration": time.monotonic() - started,
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
    }


class AgentSpawner:
    """Spawn competing agents and collect their outputs."""

    def __init__(
        self,
        claude_bin: str = "claude",
        codex_bin: str = "codex",
        dry_run: bool = False,
    ) -> None:
        self.claude_bin = claude_bin
        self.codex_bin = codex_bin
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_all(self, task: NomonTask, base_dir: Path) -> Dict[str, SpawnResult]:
        return asyncio.run(self.async_spawn_all(task, base_dir))

    async def async_spawn_all(
        self, task: NomonTask, base_dir: Path
    ) -> Dict[str, SpawnResult]:
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        coros = []
        for agent in task.agents:
            agent_dir = base_dir / agent
            self._prepare_dir(agent_dir, task, base_dir)
            if agent == "claude-code":
                coros.append(self._spawn_claude_code(task, agent_dir))
            elif agent == "codex":
                coros.append(self._spawn_codex(task, agent_dir))
            else:
                coros.append(self._unsupported(agent, agent_dir))

        results = await asyncio.gather(*coros, return_exceptions=False)
        return {r.agent: r for r in results}

    # ------------------------------------------------------------------
    # Implementations
    # ------------------------------------------------------------------

    def _prepare_dir(self, agent_dir: Path, task: NomonTask, base_dir: Path) -> None:
        """Create per-agent output dir and seed it with the working directory if any."""
        agent_dir.mkdir(parents=True, exist_ok=True)
        seed = _resolve_working_dir(task, base_dir.parent if base_dir.parent.exists() else base_dir)
        if (
            seed != agent_dir
            and seed.exists()
            and seed.is_dir()
            and not any(agent_dir.iterdir())
        ):
            try:
                for child in seed.iterdir():
                    target = agent_dir / child.name
                    if child.is_dir():
                        shutil.copytree(child, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(child, target)
            except Exception:
                pass

    async def _spawn_claude_code(
        self, task: NomonTask, output_dir: Path
    ) -> SpawnResult:
        prompt = _build_prompt(task)
        if self.dry_run:
            (output_dir / "DRY_RUN.txt").write_text(
                f"[claude-code dry-run]\n{prompt}\n", encoding="utf-8"
            )
            return SpawnResult(
                agent="claude-code",
                output_dir=output_dir,
                exit_code=0,
                duration_seconds=0.0,
                skipped=True,
                note="dry_run=True",
            )
        if not shutil.which(self.claude_bin):
            return SpawnResult(
                agent="claude-code",
                output_dir=output_dir,
                exit_code=127,
                duration_seconds=0.0,
                skipped=True,
                note=f"binary {self.claude_bin!r} not found on PATH",
            )

        argv = [
            self.claude_bin,
            "--print",
            "--permission-mode",
            "bypassPermissions",
            prompt,
        ]
        result = await _run_subprocess(argv, output_dir, task.timeout_seconds)
        return SpawnResult(
            agent="claude-code",
            output_dir=output_dir,
            exit_code=result["exit_code"],
            duration_seconds=result["duration"],
            stdout=result["stdout"],
            stderr=result["stderr"],
        )

    async def _spawn_codex(self, task: NomonTask, output_dir: Path) -> SpawnResult:
        prompt = _build_prompt(task)
        if self.dry_run:
            (output_dir / "DRY_RUN.txt").write_text(
                f"[codex dry-run]\n{prompt}\n", encoding="utf-8"
            )
            return SpawnResult(
                agent="codex",
                output_dir=output_dir,
                exit_code=0,
                duration_seconds=0.0,
                skipped=True,
                note="dry_run=True",
            )
        if not shutil.which(self.codex_bin):
            return SpawnResult(
                agent="codex",
                output_dir=output_dir,
                exit_code=127,
                duration_seconds=0.0,
                skipped=True,
                note=f"binary {self.codex_bin!r} not found on PATH",
            )

        argv = [self.codex_bin, prompt]
        result = await _run_subprocess(argv, output_dir, task.timeout_seconds)
        return SpawnResult(
            agent="codex",
            output_dir=output_dir,
            exit_code=result["exit_code"],
            duration_seconds=result["duration"],
            stdout=result["stdout"],
            stderr=result["stderr"],
        )

    async def _unsupported(self, agent: str, output_dir: Path) -> SpawnResult:
        return SpawnResult(
            agent=agent,
            output_dir=output_dir,
            exit_code=2,
            duration_seconds=0.0,
            skipped=True,
            note=f"unsupported agent: {agent}",
        )
