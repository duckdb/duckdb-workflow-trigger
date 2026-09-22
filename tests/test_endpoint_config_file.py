from pathlib import Path

from release_dispatcher.config import load_endpoints, matching_endpoints
from release_dispatcher.models import parse_release_state


def test_repository_endpoints_file_includes_required_hooks():
    endpoints = load_endpoints(Path("endpoints.yml"))

    hooks = {endpoint.hook for endpoint in endpoints}

    assert {"core_ready", "client_ready"} <= hooks


def test_repository_endpoints_route_python_by_release_line():
    endpoints = load_endpoints(Path("endpoints.yml"))
    commit = "0123456789abcdef0123456789abcdef01234567"
    version_20 = parse_release_state(
        event="core_ready",
        duckdb_version="v2.0.7",
        duckdb_commit=commit,
        status="success",
    )
    version_21 = parse_release_state(
        event="core_ready",
        duckdb_version="v2.1.0",
        duckdb_commit=commit,
        status="success",
    )

    selected_20 = matching_endpoints(endpoints, version_20)
    selected_21 = matching_endpoints(endpoints, version_21)
    python_20 = next(endpoint for endpoint in selected_20 if endpoint.name == "python")
    python_21 = next(endpoint for endpoint in selected_21 if endpoint.name == "python")

    assert python_20.target == "duckdb/duckdb-python/release.yml@v2.0-cyanoptera"
    assert python_20.release_line == "2.0"
    assert python_21.target == "duckdb/duckdb-python/release.yml@main"
    assert python_21.release_line == "2"
    assert {endpoint.name for endpoint in selected_20} == {
        "python",
        "java",
        "odbc",
        "benchmark",
    }
