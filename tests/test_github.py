import json

from release_dispatcher.config import Endpoint
from release_dispatcher.github import GitHubDispatcher
from release_dispatcher.models import parse_release_state


def test_build_workflow_dispatch_request_for_python_core_ready():
    endpoint = Endpoint(
        name="python",
        hook="core_ready",
        owner="duckdb",
        repo="duckdb-python",
        workflow="OnCoreReady.yml",
        inputs={
            "duckdb-sha": "{duckdb_commit}",
            "duckdb-version": "{duckdb_version}",
            "pypi-index": "prod",
        },
    )
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    request = GitHubDispatcher(token="fake", dry_run=True).build_request(endpoint, state)

    assert request.url == (
        "https://api.github.com/repos/duckdb/duckdb-python"
        "/actions/workflows/OnCoreReady.yml/dispatches"
    )
    assert request.body["ref"] == "main"
    assert request.body["inputs"] == {
        "duckdb-sha": "0123456789abcdef0123456789abcdef01234567",
        "duckdb-version": "v1.2.3",
        "pypi-index": "prod",
    }


def test_build_workflow_dispatch_request_for_client_ready():
    endpoint = Endpoint(
        name="consumer",
        hook="client_ready",
        owner="duckdb",
        repo="consumer",
        workflow="OnClientReady.yml",
        ref="stable",
        inputs={
            "duckdb-sha": "{duckdb_commit}",
            "payload": "{payload}",
        },
    )
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        client="python",
    )

    request = GitHubDispatcher(token="fake", dry_run=True).build_request(endpoint, state)

    assert request.body["ref"] == "stable"
    assert json.loads(request.body["inputs"]["payload"]) == {
        "phase": "client_ready",
        "name": "python",
    }
    assert request.body["inputs"]["duckdb-sha"] == "0123456789abcdef0123456789abcdef01234567"


def test_dry_run_logs_exact_workflow_ref_and_release_line(capsys):
    endpoint = Endpoint(
        name="python",
        hook="core_ready",
        owner="duckdb",
        repo="duckdb-python",
        workflow="release.yml",
        ref="v2.0-cyanoptera",
        release_line="2.0",
    )
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v2.0.7",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    GitHubDispatcher(token="fake", dry_run=True).dispatch(endpoint, state)

    assert (
        "DRY RUN: would dispatch core_ready.python for DuckDB v2.0.7 "
        "(release line 2.0) to duckdb/duckdb-python/release.yml@v2.0-cyanoptera"
    ) in capsys.readouterr().out
