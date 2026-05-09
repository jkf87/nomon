"""
Gnomon evaluation gates — pluggable evaluators for agent outputs.
"""
from __future__ import annotations

from openclaw_gnomon.gates.base import EvalGate, GateResult
from openclaw_gnomon.gates.blog_gate import BlogGate
from openclaw_gnomon.gates.code_gate import CodeGate
from openclaw_gnomon.gates.translation_gate import TranslationGate
from openclaw_gnomon.gates.ui_gate import UIGate
from openclaw_gnomon.gates.video_gate import VideoGate


GATES = {
    "code": CodeGate,
    "translation": TranslationGate,
    "blog": BlogGate,
    "ui": UIGate,
    "video": VideoGate,
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
    "VideoGate",
    "GATES",
    "gate_for",
]
