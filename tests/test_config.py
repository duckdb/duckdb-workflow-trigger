from pathlib import Path

from release_dispatcher.config import load_endpoints, matching_endpoints, registered_client_names
from release_dispatcher.models import parse_release_state


def test_load_endpoints_defaults_ref(tmp_path: Path):
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

    endpoints = load_endpoints(config)

    assert len(endpoints) == 1
    assert endpoints[0].ref == "main"
    assert endpoints[0].enabled is True


def test_matching_endpoints_filters_disabled_and_hook(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
endpoints:
  - name: python
    hook: core_ready
    owner: duckdb
    repo: duckdb-python
    workflow: OnCoreReady.yml
  - name: disabled
    hook: core_ready
    owner: duckdb
    repo: disabled
    workflow: OnCoreReady.yml
    enabled: false
  - name: other
    hook: client_ready
    owner: duckdb
    repo: other
    workflow: OnClientReady.yml
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

    assert [endpoint.name for endpoint in endpoints] == ["python"]


def test_registered_client_names_uses_enabled_endpoints(tmp_path: Path):
    config = tmp_path / "endpoints.yml"
    config.write_text(
        """
endpoints:
  - name: python
    hook: core_ready
    owner: duckdb
    repo: duckdb-python
    workflow: OnCoreReady.yml
  - name: disabled
    hook: core_ready
    owner: duckdb
    repo: disabled
    workflow: OnCoreReady.yml
    enabled: false
""",
        encoding="utf-8",
    )

    assert registered_client_names(load_endpoints(config)) == {"python"}
