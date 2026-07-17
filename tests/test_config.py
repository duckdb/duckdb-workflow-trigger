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
    - duckdb/duckdb-python/OnCoreReady.yml@main
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


def test_matching_endpoints_filters_by_hook(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
hooks:
  core_ready:
    - duckdb/duckdb-python/OnCoreReady.yml@main
  client_ready:
    other:
      - duckdb/other/OnClientReady.yml@stable
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
      - duckdb/foo/OnClientReady.yml@main
      - duckdb/bar/OnClientReady.yml@stable
    r:
      - duckdb/duckdb-r/OnClientReady.yml@stable
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
        - duckdb/duckdb-python/OnClientReady.yml@main
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
    - duckdb/duckdb-python/OnCoreReady.yml@main
  client_ready:
    r:
      - duckdb/duckdb-r/OnClientReady.yml@main
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
    - duckdb/duckdb-python/OnCoreReady.yml
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must include @ref"):
        load_endpoints(config)
