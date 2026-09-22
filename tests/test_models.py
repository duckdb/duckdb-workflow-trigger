import pytest

from release_dispatcher.models import parse_release_state


def test_core_ready_state_path_and_payload():
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    assert state.state_key == "v1.2.3/core/state.json"
    assert state.outbound_payload == {"phase": "core_ready"}
    assert state.should_dispatch is True


def test_client_ready_state_path_and_payload():
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
    )

    assert state.state_key == "v1.2.3/clients/python/state.json"
    assert state.outbound_payload == {"phase": "client_ready", "name": "python"}
    assert state.to_json_dict()["name"] == "python"
    assert "client" not in state.to_json_dict()


def test_client_ready_accepts_client_alias():
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        client="python",
    )

    assert state.name == "python"
    assert state.to_json_dict()["name"] == "python"
    assert "client" not in state.to_json_dict()


def test_client_ready_accepts_matching_name_and_client():
    state = parse_release_state(
        event="client_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="python",
        client="python",
    )

    assert state.name == "python"


def test_client_ready_rejects_conflicting_name_and_client():
    with pytest.raises(ValueError, match="name and client must match"):
        parse_release_state(
            event="client_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            name="python",
            client="r",
        )


def test_client_ready_requires_name_or_client():
    with pytest.raises(ValueError, match="name or client is required"):
        parse_release_state(
            event="client_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
        )


def test_core_ready_rejects_name():
    with pytest.raises(ValueError, match="name and client must be omitted"):
        parse_release_state(
            event="core_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            name="python",
        )


def test_check_state_path_and_payload():
    state = parse_release_state(
        event="check",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        name="benchmark",
    )

    assert state.state_key == "v1.2.3/checks/benchmark/state.json"
    assert state.outbound_payload == {"phase": "check", "name": "benchmark"}
    assert state.to_json_dict()["name"] == "benchmark"


def test_check_requires_name():
    with pytest.raises(ValueError, match="name is required for check"):
        parse_release_state(
            event="check",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
        )


def test_check_rejects_client_alias():
    with pytest.raises(ValueError, match="client must be omitted for check"):
        parse_release_state(
            event="check",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            name="benchmark",
            client="benchmark",
        )


def test_message_max_length():
    with pytest.raises(ValueError, match="message must be at most"):
        parse_release_state(
            event="core_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            message="x" * 1001,
        )


def test_failure_status_does_not_dispatch():
    state = parse_release_state(
        event="core_ready",
        duckdb_version="v1.2.3",
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="failure",
    )

    assert state.should_dispatch is False
