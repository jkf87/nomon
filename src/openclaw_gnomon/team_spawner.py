"""Team spawner — orchestrate Claude Code + Codex as parallel agents."""

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Role(str, Enum):
    ARCHITECT = "architect"
    VERIFIER_BUILDER = "verifier-builder"
    WRITER_RUNNER = "writer-runner"
    JUDGE = "judge"
    INTEGRATOR = "integrator"


class AgentRuntime(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"


@dataclass
class AgentConfig:
    role: Role
    runtime: AgentRuntime
    model: str = ""
    context: str = "isolated"  # isolated | fork
    timeout_seconds: int = 600


# Default team composition
DEFAULT_TEAM: list[AgentConfig] = [
    AgentConfig(
        role=Role.ARCHITECT,
        runtime=AgentRuntime.CLAUDE_CODE,
        model="opus",
        context="fork",
    ),
    AgentConfig(
        role=Role.VERIFIER_BUILDER,
        runtime=AgentRuntime.CODEX,
        model="codex",
        context="isolated",
    ),
    AgentConfig(
        role=Role.WRITER_RUNNER,
        runtime=AgentRuntime.CLAUDE_CODE,
        model="sonnet",
        context="isolated",
    ),
    AgentConfig(
        role=Role.JUDGE,
        runtime=AgentRuntime.CLAUDE_CODE,
        model="opus",
        context="isolated",  # 분리 컨텍스트 — writer와 다른 세션
    ),
    AgentConfig(
        role=Role.INTEGRATOR,
        runtime=AgentRuntime.CLAUDE_CODE,
        model="sonnet",
        context="isolated",
    ),
]


def build_prompt(role: Role, rubric_path: Path, workspace: Path) -> str:
    """Generate the prompt for each agent role."""

    rubric_content = rubric_path.read_text() if rubric_path.exists() else "RUBRIC_NOT_FOUND"

    prompts = {
        Role.ARCHITECT: f"""You are the architect. Design and validate the rubric schema.

Read the rubric at {rubric_path}:
{rubric_content}

Ensure:
- Every criterion has a label: quantitative, persona-llm, or human
- Quantitative ratio >= 30%
- persona-llm items have persona_ref
- human items have sample_n >= 3

Output a validated rubric.yaml to {workspace}/rubric-validated.yaml
""",
        Role.VERIFIER_BUILDER: f"""You are the verifier-builder. Implement quantitative checkers.

Read the rubric at {rubric_path}:
{rubric_content}

For each quantitative criterion, implement a Python function that:
- Takes input data
- Returns {{"pass": bool, "score": float, "detail": str}}

Write all checkers to {workspace}/checkers.py
Write a test file to {workspace}/test_checkers.py
""",
        Role.WRITER_RUNNER: f"""You are the writer-runner. Generate output that passes the rubric.

Read the rubric at {rubric_path}:
{rubric_content}

Generate output that satisfies ALL criteria.
Write results to {workspace}/output/
""",
        Role.JUDGE: f"""You are the judge. Evaluate the output against the rubric.

Read the rubric at {rubric_path}:
{rubric_content}

Evaluate the output at {workspace}/output/

For each criterion, return:
- id: criterion id
- pass: bool
- score: float
- detail: one-line explanation

Write results to {workspace}/verdict.json
If any criterion FAILS, write a fix hints file to {workspace}/fix_hints.md
""",
        Role.INTEGRATOR: f"""You are the integrator. Collect all results and create a summary.

Read:
- Rubric: {rubric_path}
- Verdict: {workspace}/verdict.json
- Output: {workspace}/output/

If all criteria PASS: write {workspace}/final/summary.md with results.
If any FAIL: write {workspace}/final/summary.md with what needs fixing.
""",
    }

    return prompts.get(role, "Unknown role")


@dataclass
class SpawnResult:
    role: Role
    runtime: AgentRuntime
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    artifacts: list[Path] = field(default_factory=list)


def spawn_agent(
    config: AgentConfig,
    rubric_path: Path,
    workspace: Path,
) -> SpawnResult:
    """Spawn a single agent and wait for completion."""

    workspace.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(config.role, rubric_path, workspace)

    prompt_file = workspace / f"prompt-{config.role.value}.md"
    prompt_file.write_text(prompt)

    try:
        if config.runtime == AgentRuntime.CLAUDE_CODE:
            result = subprocess.run(
                ["claude", "--print", "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                cwd=str(workspace),
            )
        elif config.runtime == AgentRuntime.CODEX:
            result = subprocess.run(
                ["codex", "--quiet", prompt],
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                cwd=str(workspace),
            )
        else:
            return SpawnResult(
                role=config.role,
                runtime=config.runtime,
                exit_code=1,
                stderr=f"Unknown runtime: {config.runtime}",
            )

        return SpawnResult(
            role=config.role,
            runtime=config.runtime,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    except subprocess.TimeoutExpired:
        return SpawnResult(
            role=config.role,
            runtime=config.runtime,
            exit_code=124,
            stderr="Agent timed out",
        )
    except FileNotFoundError:
        return SpawnResult(
            role=config.role,
            runtime=config.runtime,
            exit_code=127,
            stderr=f"{config.runtime.value} not found on PATH",
        )


def spawn_team(
    rubric_path: Path,
    workspace: Path | None = None,
    team: list[AgentConfig] | None = None,
) -> dict[str, Any]:
    """Spawn the full team in sequence: architect → verifier-builder → writer → judge → integrator.

    Returns a summary of all results.
    """
    if team is None:
        team = DEFAULT_TEAM
    if workspace is None:
        workspace = Path(tempfile.mkdtemp(prefix="nomon-"))

    workspace = Path(workspace)
    rubric_path = Path(rubric_path)

    results: list[SpawnResult] = []
    verdict = {"all_pass": False, "retry_count": 0, "max_retries": 5}

    # Phase 1: Architect validates rubric
    arch_result = spawn_agent(team[0], rubric_path, workspace / "architect")
    results.append(arch_result)

    if arch_result.exit_code != 0:
        return {
            "status": "architect_failed",
            "results": [vars(r) for r in results],
            "workspace": str(workspace),
        }

    validated_rubric = workspace / "architect" / "rubric-validated.yaml"
    effective_rubric = validated_rubric if validated_rubric.exists() else rubric_path

    # Phase 2: Verifier-builder creates checkers
    vb_result = spawn_agent(team[1], effective_rubric, workspace / "verifier-builder")
    results.append(vb_result)

    # Phase 3: Writer generates output (loop with judge)
    for attempt in range(verdict["max_retries"]):
        writer_result = spawn_agent(team[2], effective_rubric, workspace / f"writer-run-{attempt}")
        results.append(writer_result)

        judge_result = spawn_agent(team[3], effective_rubric, workspace / f"judge-run-{attempt}")
        results.append(judge_result)

        verdict_path = workspace / f"judge-run-{attempt}" / "verdict.json"
        if verdict_path.exists():
            with open(verdict_path) as f:
                verdict_data = json.load(f)
            all_pass = all(
                c.get("pass", False) for c in verdict_data.get("criteria", [])
            )
            if all_pass:
                verdict["all_pass"] = True
                verdict["retry_count"] = attempt
                break

        verdict["retry_count"] = attempt + 1

    # Phase 4: Integrator collects
    int_result = spawn_agent(team[4], effective_rubric, workspace / "integrator")
    results.append(int_result)

    return {
        "status": "pass" if verdict["all_pass"] else "needs_human_review",
        "retry_count": verdict["retry_count"],
        "all_pass": verdict["all_pass"],
        "results": [vars(r) for r in results],
        "workspace": str(workspace),
    }
