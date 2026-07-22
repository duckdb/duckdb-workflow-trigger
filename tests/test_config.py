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
        client="python",
    )

    endpoints = matching_endpoints(load_endpoints(config), state)

    assert [endpoint.name for endpoint in endpoints] == ["python", "python"]
    assert [(endpoint.repo, endpoint.workflow, endpoint.ref) for endpoint in endpoints] == [
        ("foo", "OnClientReady.yml", "main"),
        ("bar", "OnClientReady.yml", "stable"),
    ]


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
        client="python",
        source_run_url="https://github.com/duckdb/duckdb/actions/runs/123",
    )

    assert endpoint.render_inputs(state) == {
        "duckdb-sha": "0123456789abcdef0123456789abcdef01234567",
        "duckdb-version": "v1.2.3",
        "payload": '{"name": "python", "phase": "client_ready"}',
        "source": "https://github.com/duckdb/duckdb/actions/runs/123",
        "static": "prod",
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
