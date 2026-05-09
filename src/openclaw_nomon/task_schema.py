"""
Nomon task schema — definitions for evaluation tasks.

A `task.yaml` describes:
1. WHAT to evaluate (code/translation/blog/UI)
2. WHICH agents compete (claude-code, codex, ...)
3. HOW to score them (gate-specific spec fields)
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, ValidationError


TaskType = Literal["code", "translation", "blog", "ui"]
AgentName = Literal["claude-code", "codex"]


class CodeTaskSpec(BaseModel):
    prompt: str
    working_dir: str = "."
    test_command: Optional[str] = None
    type_check_cmd: Optional[str] = None
    lint_cmd: Optional[str] = None
    build_cmd: Optional[str] = None


class TranslationTaskSpec(BaseModel):
    prompt: Optional[str] = None
    source_path: str
    target_lang: str
    reference_path: Optional[str] = None
    proper_nouns: List[str] = Field(default_factory=list)
    length_ratio_min: float = 0.8
    length_ratio_max: float = 1.3


class BlogTaskSpec(BaseModel):
    prompt: Optional[str] = None
    content_path: str
    check_links: bool = True
    check_spelling: bool = False
    check_image_alt: bool = True


class UITaskSpec(BaseModel):
    prompt: Optional[str] = None
    url: Optional[str] = None
    html_path: Optional[str] = None
    screenshot_before: Optional[str] = None
    wcag_level: Literal["AA", "AAA"] = "AA"


TaskSpec = Annotated[
    Union[CodeTaskSpec, TranslationTaskSpec, BlogTaskSpec, UITaskSpec],
    Field(discriminator=None),
]


_SPEC_BY_TYPE = {
    "code": CodeTaskSpec,
    "translation": TranslationTaskSpec,
    "blog": BlogTaskSpec,
    "ui": UITaskSpec,
}


class NomonTask(BaseModel):
    name: str
    task_type: TaskType
    spec: dict
    agents: List[AgentName] = Field(default_factory=lambda: ["claude-code", "codex"])
    timeout_seconds: int = 300

    def parsed_spec(
        self,
    ) -> Union[CodeTaskSpec, TranslationTaskSpec, BlogTaskSpec, UITaskSpec]:
        spec_cls = _SPEC_BY_TYPE[self.task_type]
        return spec_cls(**self.spec)


class TaskSchemaError(Exception):
    """Raised when a task definition is invalid."""


def load_task(path: Path) -> NomonTask:
    """Load a task from a YAML file and validate the spec block."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    try:
        task = NomonTask(**data)
    except ValidationError as exc:
        raise TaskSchemaError(f"Invalid task at {path}: {exc}") from exc

    try:
        task.parsed_spec()
    except ValidationError as exc:
        raise TaskSchemaError(
            f"Invalid spec for task_type={task.task_type} in {path}: {exc}"
        ) from exc

    if not task.agents:
        raise TaskSchemaError(f"Task {task.name}: at least one agent required")

    return task
