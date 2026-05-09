"""Base types for nomon evaluation gates."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Protocol


@dataclass
class GateResult:
    name: str
    passed: bool
    score: float  # 0-100
    details: Dict[str, Any] = field(default_factory=dict)


class EvalGate(Protocol):
    name: str

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult: ...
