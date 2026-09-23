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


def write_versioned_config(path: Path):
    path.write_text(
        """
hooks:
  core_ready:
    python:
      "2.0":
        - workflow: duckdb/duckdb-python/release.yml@v2.0-cyanoptera
          inputs:
            duckdb-version: "{duckdb_version}"
      "2":
        - workflow: duckdb/duckdb-python/release.yml@main
          inputs:
            duckdb-version: "{duckdb_version}"
""",
        encoding="utf-8",
    )


def write_failure_dispatch_config(path: Path):
    path.write_text(
        """
hooks:
  check:
    benchmark:
      "2":
        - workflow: duckdblabs/duckdb-dev-dashboard/update_dashboard.yml@main
          inputs: null
          status: [failure, success]
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


def test_cli_dispatches_failure_to_endpoint_configured_for_failure(
    tmp_path, monkeypatch
):
    config = tmp_path / "endpoints.yml"
    write_failure_dispatch_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = set()
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "check",
            "--name",
            "benchmark",
            "--duckdb-version",
            "v2.0.7",
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
    assert FakeStore.created[0].status == "failure"
    assert [endpoint.repo for endpoint, _state, _request in FakeDispatcher.dispatched] == [
        "duckdb-dev-dashboard"
    ]


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
    assert FakeStore.created[0].name == "r"
    assert "WARNING: client 'r' is not registered" in captured.err


def test_cli_rejects_unconfigured_release_line_before_writing_state(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "endpoints.yml"
    write_versioned_config(config)
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
            "v3.0.0",
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
    assert FakeStore.created == []
    assert FakeDispatcher.attempted == []
    assert "no release line for DuckDB v3.0.0 in endpoint core_ready.python" in captured.err


def test_cli_logs_selected_workflow_and_release_line(tmp_path, monkeypatch, capsys):
    config = tmp_path / "endpoints.yml"
    write_versioned_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = set()
    monkeypatch.delenv("DRY_RUN_GITHUB", raising=False)
    monkeypatch.setattr(cli, "S3StateStore", FakeStore)
    monkeypatch.setattr(cli, "GitHubDispatcher", FakeDispatcher)

    result = cli.main(
        [
            "--event",
            "core_ready",
            "--duckdb-version",
            "v2.0.7",
            "--duckdb-commit",
            "0123456789abcdef0123456789abcdef01234567",
            "--status",
            "success",
            "--endpoint-config",
            str(config),
            "--bucket",
            "duckdb-release-state",
            "--github-token",
            "fake",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert (
        "Dispatched core_ready.python for DuckDB v2.0.7 (release line 2.0) to "
        "duckdb/duckdb-python/release.yml@v2.0-cyanoptera"
    ) in captured.out


def test_cli_stores_successful_named_check_without_registered_endpoint(
    tmp_path, monkeypatch, capsys
):
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
            "check",
            "--name",
            "benchmark",
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

    assert result == 0
    assert FakeStore.created[0].state_key == "v1.2.3/checks/benchmark/state.json"
    assert FakeDispatcher.dispatched == []
    assert "No endpoints registered for hook check" in capsys.readouterr().out


def test_cli_continues_dispatching_after_endpoint_failure(tmp_path, monkeypatch, capsys):
    config = tmp_path / "endpoints.yml"
    write_multi_endpoint_config(config)
    FakeStore.created = []
    FakeDispatcher.attempted = []
    FakeDispatcher.dispatched = []
    FakeDispatcher.failing_repos = {"missing-workflow"}
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("DRY_RUN_GITHUB", raising=False)
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
            "--github-token",
            "fake",
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
    assert (
        "Dispatched core_ready for DuckDB v1.2.3 to "
        "duckdb/duckdb-python/OnCoreReady.yml@main"
    ) in captured.out
    assert (
        "ERROR: Failed to dispatch core_ready for DuckDB v1.2.3 to "
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
            "--github-token",
            "fake",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert (
        "::error::Failed to dispatch core_ready for DuckDB v1.2.3 to "
        "duckdb/missing-workflow/OnCoreReady.yml@main: 404 Client Error"
    ) in captured.err
    assert "ERROR: 1 dispatch(es) failed" in captured.err
