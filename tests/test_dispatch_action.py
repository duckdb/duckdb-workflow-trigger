import os
import subprocess
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
        "name",
        "client",
        "source_run_url",
        "message",
    } <= set(action["inputs"])

    for name in ["github_token", "event", "duckdb_version", "duckdb_commit", "status"]:
        assert action["inputs"][name]["required"] is True

    assert action["inputs"]["name"]["required"] is False
    assert action["inputs"]["client"]["required"] is False


def test_dispatch_action_normalizes_named_events():
    action = load_action()
    script = action["runs"]["steps"][0]["run"]

    assert "name or client is required for client_ready" in script
    assert "name is required for check" in script
    assert 'args+=(--field "name=$name")' in script
    assert 'args+=(--field "client=$DISPATCH_CLIENT")' not in script


def test_dispatch_action_forwards_check_name(tmp_path: Path):
    result, args = run_action(
        tmp_path,
        event="check",
        name="benchmark",
    )

    assert result.returncode == 0
    assert "event=check" in args
    assert "name=benchmark" in args
    assert not any(arg.startswith("client=") for arg in args)


def test_dispatch_action_normalizes_legacy_client_input(tmp_path: Path):
    result, args = run_action(
        tmp_path,
        event="client_ready",
        client="python",
    )

    assert result.returncode == 0
    assert "event=client_ready" in args
    assert "name=python" in args
    assert not any(arg.startswith("client=") for arg in args)


def test_dispatch_action_rejects_check_without_name(tmp_path: Path):
    result, args = run_action(tmp_path, event="check")

    assert result.returncode == 1
    assert "name is required for check" in result.stderr
    assert args == []


def test_dispatch_action_rejects_conflicting_client_names(tmp_path: Path):
    result, args = run_action(
        tmp_path,
        event="client_ready",
        name="python",
        client="r",
    )

    assert result.returncode == 1
    assert "name and client must match" in result.stderr
    assert args == []


def run_action(
    tmp_path: Path,
    *,
    event: str,
    name: str = "",
    client: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    action = load_action()
    script = action["runs"]["steps"][0]["run"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "gh-args"
    gh = bin_dir / "gh"
    gh.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$GH_ARGS_FILE"\n', encoding="utf-8")
    gh.chmod(0o755)
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_ARGS_FILE": str(args_file),
        "DISPATCH_EVENT": event,
        "DISPATCH_DUCKDB_VERSION": "v1.2.3",
        "DISPATCH_DUCKDB_COMMIT": "0123456789abcdef0123456789abcdef01234567",
        "DISPATCH_STATUS": "success",
        "DISPATCH_NAME": name,
        "DISPATCH_CLIENT": client,
        "DISPATCH_SOURCE_RUN_URL": "",
        "DISPATCH_MESSAGE": "",
        "DEFAULT_SOURCE_RUN_URL": "https://github.com/duckdb/example/actions/runs/123",
    }
    result = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    args = args_file.read_text(encoding="utf-8").splitlines() if args_file.exists() else []
    return result, args
