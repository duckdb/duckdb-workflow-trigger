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
        client="python",
    )

    assert state.state_key == "v1.2.3/clients/python/state.json"
    assert state.outbound_payload == {"phase": "client_ready", "name": "python"}


def test_client_ready_requires_client():
    with pytest.raises(ValueError, match="client is required"):
        parse_release_state(
            event="client_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
        )


def test_core_ready_rejects_client():
    with pytest.raises(ValueError, match="client must be omitted"):
        parse_release_state(
            event="core_ready",
            duckdb_version="v1.2.3",
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            client="python",
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
