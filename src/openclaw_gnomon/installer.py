import json
from pathlib import Path


def merge_mcp_entry(mcp_config_path: Path) -> None:
    """Add nomon MCP server entry to config. Idempotent."""
    mcp_config_path = Path(mcp_config_path)
    mcp_config_path.parent.mkdir(parents=True, exist_ok=True)

    if mcp_config_path.exists():
        with open(mcp_config_path) as f:
            config = json.load(f)
    else:
        config = {"mcpServers": {}}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if "nomon" not in config["mcpServers"]:
        config["mcpServers"]["nomon"] = {
            "type": "stdio",
            "command": "uvx",
            "args": ["--from", "nomon[mcp]", "nomon", "mcp", "serve"]
        }

    with open(mcp_config_path, "w") as f:
        json.dump(config, f, indent=2)


def remove_mcp_entry(mcp_config_path: Path) -> None:
    """Remove nomon MCP server entry from config. Idempotent."""
    mcp_config_path = Path(mcp_config_path)
    if not mcp_config_path.exists():
        return

    with open(mcp_config_path) as f:
        config = json.load(f)

    if "mcpServers" in config:
        config["mcpServers"].pop("nomon", None)

    with open(mcp_config_path, "w") as f:
        json.dump(config, f, indent=2)


def stage_skill_files(skills_dir: Path) -> None:
    """Copy SKILL.md from package template to ~/.openclaw/skills/nomon/SKILL.md."""
    skills_dir = Path(skills_dir)
    skill_target_dir = skills_dir / "nomon"
    skill_target_dir.mkdir(parents=True, exist_ok=True)

    import importlib.resources
    try:
        from importlib.resources import files
        skill_template_file = files("openclaw_gnomon.skill_template").joinpath("SKILL.md")
        skill_content = skill_template_file.read_text()
    except (ImportError, TypeError):
        import pkg_resources
        skill_content = pkg_resources.resource_string(
            "openclaw_gnomon.skill_template", "SKILL.md"
        ).decode("utf-8")

    target_file = skill_target_dir / "SKILL.md"
    with open(target_file, "w") as f:
        f.write(skill_content)


def write_nomon_config(config_path: Path) -> None:
    """Write ~/.nomon/config.yaml with runtime_backend: openclaw."""
    import yaml
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "orchestrator" not in config:
        config["orchestrator"] = {}

    config["orchestrator"]["runtime_backend"] = "openclaw"

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
