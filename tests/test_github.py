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
    assert request.body["inputs"]["duckdb_version"] == "v1.2.3"
    assert request.body["inputs"]["duckdb_commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert json.loads(request.body["inputs"]["payload"]) == {"phase": "core_ready"}


def test_build_workflow_dispatch_request_for_client_ready():
    endpoint = Endpoint(
        name="consumer",
        hook="client_ready",
        owner="duckdb",
        repo="consumer",
        workflow="OnClientReady.yml",
        ref="stable",
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
