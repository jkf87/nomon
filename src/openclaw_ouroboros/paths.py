import os
from pathlib import Path


def openclaw_skills_dir() -> Path:
    """Return ~/.openclaw/skills directory. Override with OPENCLAW_SKILLS_DIR env var."""
    env = os.environ.get("OPENCLAW_SKILLS_DIR")
    if env:
        return Path(env)
    home = Path.home()
    return home / ".openclaw" / "skills"


def openclaw_mcp_config_path() -> Path:
    """Return ~/.openclaw/mcp/claude-mcp-config.json path. Override with OPENCLAW_MCP_CONFIG env var."""
    env = os.environ.get("OPENCLAW_MCP_CONFIG")
    if env:
        return Path(env)
    home = Path.home()
    return home / ".openclaw" / "mcp" / "claude-mcp-config.json"


def ouroboros_config_path() -> Path:
    """Return ~/.ouroboros/config.yaml path. Override with OUROBOROS_CONFIG env var."""
    env = os.environ.get("OUROBOROS_CONFIG")
    if env:
        return Path(env)
    home = Path.home()
    return home / ".ouroboros" / "config.yaml"
