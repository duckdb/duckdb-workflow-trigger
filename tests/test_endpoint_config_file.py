from pathlib import Path

import pytest

from release_dispatcher.config import load_endpoints, matching_endpoints
from release_dispatcher.models import parse_release_state


def test_repository_endpoints_file_includes_required_hooks():
    endpoints = load_endpoints(Path("endpoints.yml"))

    hooks = {endpoint.hook for endpoint in endpoints}

    assert {"core_ready", "client_ready", "check"} <= hooks


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
        "duckdb-rs",
    }


def test_repository_endpoints_apply_and_replace_default_inputs():
    endpoints = load_endpoints(Path("endpoints.yml"))
    commit = "0123456789abcdef0123456789abcdef01234567"
    core_state = parse_release_state(
        event="core_ready",
        duckdb_version="v2.0.7",
        duckdb_commit=commit,
        status="success",
    )
    client_state = parse_release_state(
        event="client_ready",
        duckdb_version="v2.0.7",
        duckdb_commit=commit,
        status="success",
        client="r",
    )

    core = {endpoint.name: endpoint for endpoint in matching_endpoints(endpoints, core_state)}
    expected_defaults = {
        "duckdb-sha": commit,
        "duckdb-version": "v2.0.7",
    }

    assert core["python"].render_inputs(core_state) == {
        **expected_defaults,
        "pypi-index": "prod",
    }
    assert core["java"].render_inputs(core_state) == expected_defaults
    assert core["odbc"].render_inputs(core_state) == expected_defaults
    assert core["benchmark"].render_inputs(core_state) == expected_defaults

    [r_endpoint] = matching_endpoints(endpoints, client_state)
    assert r_endpoint.render_inputs(client_state) == {
        "duckdb_version": "v2.0.7",
        "duckdb_commit": commit,
        "payload": '{"name": "r", "phase": "client_ready"}',
    }


@pytest.mark.parametrize("status", ["failure", "success"])
def test_repository_endpoints_route_v2_benchmark_check_to_dashboard_without_inputs(status):
    endpoints = load_endpoints(Path("endpoints.yml"))
    state = parse_release_state(
        event="check",
        name="benchmark",
        duckdb_version="v2.0.7",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status=status,
    )

    selected = matching_endpoints(endpoints, state)
    endpoint = next(
        endpoint
        for endpoint in selected
        if endpoint.target == "duckdblabs/duckdb-dev-dashboard/update_dashboard.yml@main"
    )

    assert endpoint.release_line == "2"
    assert endpoint.statuses == {"failure", "success"}
    assert endpoint.render_inputs(state) == {}
