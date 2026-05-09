"""
CodeGate — runs tests, type-check, lint, build commands and aggregates a score.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openclaw_gnomon.gates.base import GateResult


@dataclass
class _CmdResult:
    cmd: Optional[str]
    ran: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.ran and self.exit_code == 0


def _run(cmd: Optional[str], cwd: Path, timeout: int = 600) -> _CmdResult:
    if not cmd:
        return _CmdResult(cmd=None, ran=False, exit_code=None, stdout="", stderr="")
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return _CmdResult(
            cmd=cmd,
            ran=True,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except FileNotFoundError as exc:
        return _CmdResult(cmd=cmd, ran=False, exit_code=None, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return _CmdResult(
            cmd=cmd,
            ran=True,
            exit_code=124,
            stdout="",
            stderr=f"timeout after {exc.timeout}s",
        )


def _lint_score(result: _CmdResult) -> Tuple[float, Dict[str, Any]]:
    """Pass = 100, otherwise penalize per warning/error in stderr+stdout."""
    if not result.ran:
        return 0.0, {"reason": "lint command did not run"}
    if result.passed:
        return 100.0, {"warnings": 0}

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    warnings = output.lower().count("warning")
    errors = output.lower().count("error")
    penalty = min(100.0, errors * 10 + warnings * 2)
    return max(0.0, 100.0 - penalty), {"warnings": warnings, "errors": errors}


class CodeGate:
    name = "code"

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult:
        cwd = Path(output_dir)
        if not cwd.exists():
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": f"output dir missing: {cwd}"},
            )

        test = _run(getattr(task_spec, "test_command", None), cwd)
        types = _run(getattr(task_spec, "type_check_cmd", None), cwd)
        lint = _run(getattr(task_spec, "lint_cmd", None), cwd)
        build = _run(getattr(task_spec, "build_cmd", None), cwd)

        scores = []
        details: Dict[str, Any] = {}

        if test.ran:
            scores.append(100.0 if test.passed else 0.0)
            details["test"] = {"passed": test.passed, "exit_code": test.exit_code}
        if types.ran:
            scores.append(100.0 if types.passed else 0.0)
            details["type_check"] = {"passed": types.passed, "exit_code": types.exit_code}
        if lint.ran:
            score, ldetails = _lint_score(lint)
            scores.append(score)
            details["lint"] = {"passed": lint.passed, **ldetails}
        if build.ran:
            scores.append(100.0 if build.passed else 0.0)
            details["build"] = {"passed": build.passed, "exit_code": build.exit_code}

        if not scores:
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": "no commands configured", **details},
            )

        avg = sum(scores) / len(scores)
        all_pass = (
            (not test.ran or test.passed)
            and (not types.ran or types.passed)
            and (not build.ran or build.passed)
            and (not lint.ran or _lint_score(lint)[0] >= 70.0)
        )
        return GateResult(name=self.name, passed=all_pass, score=avg, details=details)
