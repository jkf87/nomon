"""Tests for openclaw_gnomon.task_schema."""
import pytest
import yaml

from openclaw_gnomon.task_schema import (
    BlogTaskSpec,
    CodeTaskSpec,
    GnomonTask,
    TaskSchemaError,
    TranslationTaskSpec,
    UITaskSpec,
    load_task,
)


def _write_yaml(tmp_path, data):
    path = tmp_path / "task.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_load_code_task(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Refactor",
            "task_type": "code",
            "spec": {
                "prompt": "do the thing",
                "test_command": "pytest",
            },
            "agents": ["claude-code", "codex"],
        },
    )
    task = load_task(path)
    assert isinstance(task, GnomonTask)
    assert task.task_type == "code"
    spec = task.parsed_spec()
    assert isinstance(spec, CodeTaskSpec)
    assert spec.test_command == "pytest"


def test_load_translation_task(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Translate",
            "task_type": "translation",
            "spec": {
                "source_path": "docs/en",
                "target_lang": "ko",
                "proper_nouns": ["Claude"],
            },
            "agents": ["claude-code"],
        },
    )
    task = load_task(path)
    spec = task.parsed_spec()
    assert isinstance(spec, TranslationTaskSpec)
    assert spec.target_lang == "ko"
    assert spec.proper_nouns == ["Claude"]


def test_load_blog_task(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Blog",
            "task_type": "blog",
            "spec": {"content_path": "post"},
            "agents": ["codex"],
        },
    )
    task = load_task(path)
    spec = task.parsed_spec()
    assert isinstance(spec, BlogTaskSpec)
    assert spec.content_path == "post"


def test_load_ui_task(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "UI",
            "task_type": "ui",
            "spec": {"html_path": "index.html", "wcag_level": "AAA"},
            "agents": ["claude-code"],
        },
    )
    task = load_task(path)
    spec = task.parsed_spec()
    assert isinstance(spec, UITaskSpec)
    assert spec.wcag_level == "AAA"


def test_load_task_invalid_type(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Bad",
            "task_type": "unknown",
            "spec": {},
            "agents": ["claude-code"],
        },
    )
    with pytest.raises(TaskSchemaError):
        load_task(path)


def test_load_task_missing_required_spec_field(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Bad",
            "task_type": "translation",
            "spec": {"target_lang": "ko"},
            "agents": ["claude-code"],
        },
    )
    with pytest.raises(TaskSchemaError):
        load_task(path)


def test_load_task_requires_agent(tmp_path):
    path = _write_yaml(
        tmp_path,
        {
            "name": "Empty",
            "task_type": "code",
            "spec": {"prompt": "p"},
            "agents": [],
        },
    )
    with pytest.raises(TaskSchemaError):
        load_task(path)
