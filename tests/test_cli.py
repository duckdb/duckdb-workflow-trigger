from pathlib import Path

import requests

from release_dispatcher import cli


class FakeStore:
    created = []

    def __init__(self, _settings):
        pass

    def create_state(self, state):
        self.created.append(state)
        return state.state_key


class FakeDispatcher:
    attempted = []
    dispatched = []
    failing_repos = set()

    def __init__(self, *, token, dry_run=False, api_base="https://api.github.com", session=None):
        self.token = token
        self.dry_run = dry_run

    def dispatch(self, endpoint, state):
        self.attempted.append(endpoint)
        if endpoint.repo in self.failing_repos:
            raise requests.HTTPError("404 Client Error: Not Found for url")
        request = self.build_request(endpoint, state)
        self.dispatched.append((endpoint, state, request))
        return request

    def build_request(self, endpoint, _state):
        return type("Request", (), {"url": f"https://example.invalid/{endpoint.name}"})()


def write_config(path: Path):
    path.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        duckdb-sha: "{duckdb_commit}"
""",
        encoding="utf-8",
    )


def write_multi_endpoint_config(path: Path):
    path.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/missing-workflow/OnCoreReady.yml@main
      inputs:
        duckdb-sha: "{duckdb_commit}"
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        duckdb-sha: "{duckdb_commit}"
""",
        encoding="utf-8",
    )


def test_cli_stores_failure_without_dispatch(tmp_path, monkeypatch, capsys):
    config = tmp_path / "endpoints.yml"
    write_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = set()
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "core_ready",
            "--duckdb-version",
            "v1.2.3",
            "--duckdb-commit",
            "0123456789abcdef0123456789abcdef01234567",
            "--status",
            "failure",
            "--endpoint-config",
            str(config),
            "--bucket",
            "duckdb-release-state",
            "--dry-run-github",
        ]
    )

    assert result == 0
    assert len(FakeStore.created) == 1
    assert FakeDispatcher.dispatched == []
    assert "skipping outbound dispatch" in capsys.readouterr().out


def test_cli_warns_for_unknown_client_but_stores(tmp_path, monkeypatch, capsys):
    config = tmp_path / "endpoints.yml"
    write_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = set()
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "client_ready",
            "--duckdb-version",
            "v1.2.3",
            "--duckdb-commit",
            "0123456789abcdef0123456789abcdef01234567",
            "--status",
            "success",
            "--client",
            "r",
            "--endpoint-config",
            str(config),
            "--bucket",
            "duckdb-release-state",
            "--dry-run-github",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert FakeStore.created[0].state_key == "v1.2.3/clients/r/state.json"
    assert "WARNING: client 'r' is not registered" in captured.err


def test_cli_continues_dispatching_after_endpoint_failure(tmp_path, monkeypatch, capsys):
    config = tmp_path / "endpoints.yml"
    write_multi_endpoint_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = {"missing-workflow"}
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "core_ready",
            "--duckdb-version",
            "v1.2.3",
            "--duckdb-commit",
            "0123456789abcdef0123456789abcdef01234567",
            "--status",
            "success",
            "--endpoint-config",
            str(config),
            "--bucket",
            "duckdb-release-state",
            "--dry-run-github",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert [endpoint.repo for endpoint in FakeDispatcher.attempted] == [
        "missing-workflow",
        "duckdb-python",
    ]
    assert [endpoint.repo for endpoint, _state, _request in FakeDispatcher.dispatched] == [
        "duckdb-python"
    ]
    assert "Dispatched core_ready to https://example.invalid/core_ready" in captured.out
    assert (
        "ERROR: Failed to dispatch core_ready to "
        "duckdb/missing-workflow/OnCoreReady.yml@main: 404 Client Error"
    ) in captured.err
    assert "ERROR: 1 dispatch(es) failed" in captured.err


def test_cli_emits_github_actions_annotation_for_endpoint_failure(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "endpoints.yml"
    write_multi_endpoint_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = {"missing-workflow"}
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "core_ready",
            "--duckdb-version",
            "v1.2.3",
            "--duckdb-commit",
            "0123456789abcdef0123456789abcdef01234567",
            "--status",
            "success",
            "--endpoint-config",
            str(config),
            "--bucket",
            "duckdb-release-state",
            "--dry-run-github",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert (
        "::error::Failed to dispatch core_ready to "
        "duckdb/missing-workflow/OnCoreReady.yml@main: 404 Client Error"
    ) in captured.err
    assert "ERROR: 1 dispatch(es) failed" in captured.err
