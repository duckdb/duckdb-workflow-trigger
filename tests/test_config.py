from pathlib import Path

import pytest

from release_dispatcher.config import load_endpoints, matching_endpoints, registered_client_names
from release_dispatcher.models import parse_release_state


def test_load_endpoints_from_grouped_hooks(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        duckdb-sha: "{duckdb_commit}"
        duckdb-version: "{duckdb_version}"
""",
        encoding="utf-8",
    )

    endpoints = load_endpoints(config)

    assert len(endpoints) == 1
    assert endpoints[0].name == "core_ready"
    assert endpoints[0].hook == "core_ready"
    assert endpoints[0].owner == "duckdb"
    assert endpoints[0].repo == "duckdb-python"
    assert endpoints[0].workflow == "OnCoreReady.yml"
    assert endpoints[0].ref == "main"
    assert endpoints[0].inputs == {
        "duckdb-sha": "{duckdb_commit}",
        "duckdb-version": "{duckdb_version}",
    }


def test_load_endpoints_applies_yaml_default_inputs_to_all_hooks(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
defaults:
  inputs:
    duckdb-sha: "{duckdb_commit}"
    duckdb-version: "{duckdb_version}"
hooks:
  core_ready:
    - workflow: duckdb/core-consumer/OnCoreReady.yml@main
  client_ready:
    r:
      - workflow: duckdb/client-consumer/OnClientReady.yml@main
""",
        encoding="utf-8",
    )

    endpoints = load_endpoints(config)

    assert [endpoint.inputs for endpoint in endpoints] == [
        {
            "duckdb-sha": "{duckdb_commit}",
            "duckdb-version": "{duckdb_version}",
        },
        {
            "duckdb-sha": "{duckdb_commit}",
            "duckdb-version": "{duckdb_version}",
        },
    ]
    assert endpoints[0].inputs is not endpoints[1].inputs


def test_explicit_inputs_replace_yaml_defaults(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
defaults:
  inputs:
    duckdb-sha: "{duckdb_commit}"
    duckdb-version: "{duckdb_version}"
hooks:
  core_ready:
    - workflow: duckdb/mapping/OnCoreReady.yml@main
      inputs:
        pypi-index: prod
    - workflow: duckdb/list/OnCoreReady.yml@main
      inputs:
        - duckdb_commit
    - workflow: duckdb/null/OnCoreReady.yml@main
      inputs: null
    - workflow: duckdb/empty/OnCoreReady.yml@main
      inputs: []
""",
        encoding="utf-8",
    )

    endpoints = {endpoint.repo: endpoint for endpoint in load_endpoints(config)}

    assert endpoints["mapping"].inputs == {"pypi-index": "prod"}
    assert endpoints["list"].inputs == {"duckdb_commit": "{duckdb_commit}"}
    assert endpoints["null"].inputs is None
    assert endpoints["empty"].inputs == {}


def test_omitted_inputs_remain_empty_without_yaml_defaults(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
""",
        encoding="utf-8",
    )

    assert load_endpoints(config)[0].inputs is None


@pytest.mark.parametrize(
    ("defaults", "error"),
    [
        ("defaults: invalid", "defaults must be a mapping"),
        ("defaults:\n  inputs: invalid", "inputs must be a mapping or list"),
    ],
)
def test_load_endpoints_rejects_invalid_yaml_defaults(
    tmp_path: Path, defaults: str, error: str
):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        f"""
{defaults}
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error):
        load_endpoints(config)


def test_matching_endpoints_filters_by_hook(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
  client_ready:
    other:
      - workflow: duckdb/other/OnClientReady.yml@stable
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    endpoints = matching_endpoints(load_endpoints(config), state)

    assert [endpoint.name for endpoint in endpoints] == ["core_ready"]


def test_matching_endpoints_filters_client_ready_by_client_name(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  client_ready:
    python:
      - workflow: duckdb/foo/OnClientReady.yml@main
      - workflow: duckdb/bar/OnClientReady.yml@stable
    r:
      - workflow: duckdb/duckdb-r/OnClientReady.yml@stable
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
    )

    endpoints = matching_endpoints(load_endpoints(config), state)

    assert [endpoint.name for endpoint in endpoints] == ["python", "python"]
    assert [(endpoint.repo, endpoint.workflow, endpoint.ref) for endpoint in endpoints] == [
        ("foo", "OnClientReady.yml", "main"),
        ("bar", "OnClientReady.yml", "stable"),
    ]


def test_matching_endpoints_prefers_exact_release_line_then_major_fallback(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
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
    java:
      "2":
        - workflow: duckdb/duckdb-java/Vendor.yml@main
""",
        encoding="utf-8",
    )
    endpoints = load_endpoints(config)

    exact_state = parse_release_state(
        event="core_ready",
        duckdb_version="v2.0.7",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )
    fallback_state = parse_release_state(
        event="core_ready",
        duckdb_version="2.1.0-dev12",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    exact = matching_endpoints(endpoints, exact_state)
    fallback = matching_endpoints(endpoints, fallback_state)

    assert [(endpoint.name, endpoint.ref, endpoint.release_line) for endpoint in exact] == [
        ("python", "v2.0-cyanoptera", "2.0"),
        ("java", "main", "2"),
    ]
    assert [(endpoint.name, endpoint.ref, endpoint.release_line) for endpoint in fallback] == [
        ("python", "main", "2"),
        ("java", "main", "2"),
    ]
    assert fallback[0].render_inputs(fallback_state)["duckdb-version"] == "2.1.0-dev12"


def test_matching_endpoints_selects_release_line_for_requested_client(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  client_ready:
    python:
      "2.0":
        - workflow: duckdb/duckdb-python/OnClientReady.yml@v2.0-cyanoptera
      "2":
        - workflow: duckdb/duckdb-python/OnClientReady.yml@main
    r:
      "2":
        - workflow: duckdb/duckdb-r/OnClientReady.yml@main
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v2.0.1",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
    )

    endpoints = matching_endpoints(load_endpoints(config), state)

    assert [(endpoint.name, endpoint.ref, endpoint.release_line) for endpoint in endpoints] == [
        ("python", "v2.0-cyanoptera", "2.0")
    ]


def test_matching_endpoints_filters_check_by_name(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  check:
    benchmark:
      - workflow: duckdb/foo/AfterBenchmark.yml@main
    test:
      - workflow: duckdb/bar/AfterTests.yml@main
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="check",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="benchmark",
    )

    endpoints = matching_endpoints(load_endpoints(config), state)

    assert [(endpoint.name, endpoint.workflow) for endpoint in endpoints] == [
        ("benchmark", "AfterBenchmark.yml")
    ]


def test_matching_endpoints_filters_by_configured_status(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  check:
    benchmark:
      - workflow: duckdb/default/OnSuccess.yml@main
      - workflow: duckdb/configured/OnCompletion.yml@main
        status: [failure, success]
""",
        encoding="utf-8",
    )
    endpoints = load_endpoints(config)

    def matches(status: str) -> list[str]:
        state = parse_release_state(
            event="check",
            duckdb_version="v2.0.7",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status=status,
            name="benchmark",
        )
        return [endpoint.repo for endpoint in matching_endpoints(endpoints, state)]

    assert endpoints[0].statuses == {"success"}
    assert matches("failure") == ["configured"]
    assert matches("success") == ["default", "configured"]
    assert matches("skipped") == []


@pytest.mark.parametrize(
    "configured_status",
    [
        "success",
        "[]",
        "[success, unknown]",
        "[success, success]",
    ],
)
def test_load_endpoints_rejects_invalid_status_lists(
    tmp_path: Path, configured_status: str
):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        f"""
hooks:
  check:
    benchmark:
      - workflow: duckdb/foo/AfterBenchmark.yml@main
        status: {configured_status}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="status"):
        load_endpoints(config)


def test_matching_endpoints_rejects_unconfigured_release_line(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    python:
      "2":
        - workflow: duckdb/duckdb-python/release.yml@main
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v3.0.0",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    with pytest.raises(ValueError, match=r"no release line.*core_ready\.python"):
        matching_endpoints(load_endpoints(config), state)


def test_matching_endpoints_rejects_malformed_duckdb_version(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    python:
      "2":
        - workflow: duckdb/duckdb-python/release.yml@main
""",
        encoding="utf-8",
    )
    state = parse_release_state(
        event="core_ready",
        duckdb_version="cyanoptera",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    with pytest.raises(ValueError, match="must contain a numeric major.minor version"):
        matching_endpoints(load_endpoints(config), state)


def test_load_endpoints_requires_quoted_release_line_keys(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    python:
      2.0:
        - workflow: duckdb/duckdb-python/release.yml@main
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a quoted string"):
        load_endpoints(config)


def test_load_endpoints_rejects_wrapped_workflows_key(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  client_ready:
    python:
      workflows:
        - workflow: duckdb/duckdb-python/OnClientReady.yml@main
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a workflow list"):
        load_endpoints(config)


def test_registered_client_names_uses_grouped_endpoints(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
  client_ready:
    r:
      - workflow: duckdb/duckdb-r/OnClientReady.yml@main
""",
        encoding="utf-8",
    )

    assert registered_client_names(load_endpoints(config)) == {"r"}


def test_load_endpoints_rejects_legacy_list_schema(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
endpoints:
  - name: python
    hook: core_ready
    owner: duckdb
    repo: duckdb-python
    workflow: OnCoreReady.yml
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hooks mapping"):
        load_endpoints(config)


def test_load_endpoints_rejects_malformed_workflow_target(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must include @ref"):
        load_endpoints(config)


def test_load_endpoints_rejects_string_endpoint_entries(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - duckdb/duckdb-python/OnCoreReady.yml@main
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a mapping"):
        load_endpoints(config)


def test_load_endpoints_rejects_missing_workflow(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - inputs:
        duckdb-sha: "{duckdb_commit}"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="workflow.*must be a non-empty string"):
        load_endpoints(config)


def test_load_endpoints_accepts_input_name_list(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        - duckdb_commit
""",
        encoding="utf-8",
    )

    endpoints = load_endpoints(config)

    assert endpoints[0].inputs == {"duckdb_commit": "{duckdb_commit}"}


def test_endpoint_renders_only_input_name_list_values(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        - duckdb_commit
""",
        encoding="utf-8",
    )
    endpoint = load_endpoints(config)[0]
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    assert endpoint.render_inputs(state) == {
        "duckdb_commit": "0123456789abcdef0123456789abcdef01234567",
    }


def test_load_endpoints_rejects_unknown_input_name_list_values(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        - target_branch
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a known template value"):
        load_endpoints(config)


def test_load_endpoints_rejects_scalar_inputs(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs: duckdb_commit
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="inputs must be a mapping or list"):
        load_endpoints(config)


def test_load_endpoints_rejects_nested_input_values(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        nested:
          value: "{duckdb_commit}"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a scalar value"):
        load_endpoints(config)


def test_endpoint_renders_configured_inputs(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  client_ready:
    python:
      - workflow: duckdb/duckdb-python/Release.yml@stable
        inputs:
          duckdb-sha: "{duckdb_commit}"
          duckdb-version: "{duckdb_version}"
          payload: "{payload}"
          source: "{source_run_url}"
          static: prod
""",
        encoding="utf-8",
    )
    endpoint = load_endpoints(config)[0]
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
        source_run_url="https://github.com/duckdb/duckdb/actions/runs/123",
    )

    assert endpoint.render_inputs(state) == {
        "duckdb-sha": "0123456789abcdef0123456789abcdef01234567",
        "duckdb-version": "v1.2.3",
        "payload": '{"name": "python", "phase": "client_ready"}',
        "source": "https://github.com/duckdb/duckdb/actions/runs/123",
        "static": "prod",
    }


def test_endpoint_renders_name_and_legacy_client_alias(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  client_ready:
    python:
      - workflow: duckdb/duckdb-python/Release.yml@main
        inputs:
          name: "{name}"
          client: "{client}"
  check:
    benchmark:
      - workflow: duckdb/foo/AfterBenchmark.yml@main
        inputs:
          name: "{name}"
          client: "{client}"
""",
        encoding="utf-8",
    )
    client_endpoint, check_endpoint = load_endpoints(config)
    client_state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
    )
    check_state = parse_release_state(
        event="check",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="benchmark",
    )

    assert client_endpoint.render_inputs(client_state) == {
        "name": "python",
        "client": "python",
    }
    assert check_endpoint.render_inputs(check_state) == {
        "name": "benchmark",
        "client": "",
    }


def test_endpoint_rejects_unknown_template_fields(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/OnCoreReady.yml@main
      inputs:
        bad: "{target_branch}"
""",
        encoding="utf-8",
    )
    endpoint = load_endpoints(config)[0]
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    with pytest.raises(ValueError, match="unknown template value 'target_branch'"):
        endpoint.render_inputs(state)
