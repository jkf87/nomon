import pytest
from pathlib import Path


@pytest.fixture
def sample_mcp_config(tmp_path):
    """Fixture: create a sample mcp.json file in a temp directory"""
    import json
    config = {
        "mcpServers": {
            "openclaw": {
                "type": "stdio",
                "command": "openclaw",
                "args": ["mcp", "serve"]
            }
        }
    }
    config_file = tmp_path / "mcp.json"
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    return config_file


@pytest.fixture
def temp_home(tmp_path):
    """Fixture: temporary home directory for isolated testing"""
    import os
    original_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    yield tmp_path
    if original_home:
        os.environ["HOME"] = original_home
