from pathlib import Path

import yaml


def load_action():
    return yaml.safe_load(Path("dispatch/action.yml").read_text(encoding="utf-8"))


def test_dispatch_action_exposes_expected_inputs():
    action = load_action()

    assert action["runs"]["using"] == "composite"
    assert {
        "github_token",
        "event",
        "duckdb_version",
        "duckdb_commit",
        "status",
        "client",
        "source_run_url",
        "message",
    } <= set(action["inputs"])

    for name in ["github_token", "event", "duckdb_version", "duckdb_commit", "status"]:
        assert action["inputs"][name]["required"] is True
