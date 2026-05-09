"""
Nomon evaluation gates — pluggable evaluators for agent outputs.
"""
from __future__ import annotations

from openclaw_nomon.gates.base import EvalGate, GateResult
from openclaw_nomon.gates.blog_gate import BlogGate
from openclaw_nomon.gates.code_gate import CodeGate
from openclaw_nomon.gates.translation_gate import TranslationGate
from openclaw_nomon.gates.ui_gate import UIGate


GATES = {
    "code": CodeGate,
    "translation": TranslationGate,
    "blog": BlogGate,
    "ui": UIGate,
}


def gate_for(task_type: str) -> EvalGate:
    if task_type not in GATES:
        raise ValueError(f"No gate registered for task_type={task_type!r}")
    return GATES[task_type]()


__all__ = [
    "GateResult",
    "EvalGate",
    "CodeGate",
    "TranslationGate",
    "BlogGate",
    "UIGate",
    "GATES",
    "gate_for",
]
