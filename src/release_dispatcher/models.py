from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


ReleaseEvent = Literal["core_ready", "client_ready"]
ReleaseStatus = Literal["success", "failure", "skipped"]

VALID_EVENTS: set[str] = {"core_ready", "client_ready"}
VALID_STATUSES: set[str] = {"success", "failure", "skipped"}
MAX_MESSAGE_LENGTH = 1000


@dataclass(frozen=True)
class ReleaseState:
    event: ReleaseEvent
    duckdb_version: str
    duckdb_commit: str
    status: ReleaseStatus
    client: str | None = None
    message: str | None = None
    source_workflow: str | None = None
    source_run_id: str | None = None

    @property
    def should_dispatch(self) -> bool:
        return self.status == "success"

    @property
    def state_key(self) -> str:
        if self.event == "core_ready":
            return f"{self.duckdb_version}/core/state.json"
        if not self.client:
            raise ValueError("client is required for client_ready state paths")
        return f"{self.duckdb_version}/clients/{self.client}/state.json"

    @property
    def outbound_payload(self) -> dict[str, str]:
        if self.event == "core_ready":
            return {"phase": "core_ready"}
        if not self.client:
            raise ValueError("client is required for client_ready payloads")
        return {"phase": "client_ready", "name": self.client}

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "event": self.event,
            "duckdb_version": self.duckdb_version,
            "duckdb_commit": self.duckdb_commit,
            "status": self.status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.client is not None:
            result["client"] = self.client
        if self.message:
            result["message"] = self.message
        if self.source_workflow:
            result["source_workflow"] = self.source_workflow
        if self.source_run_id:
            result["source_run_id"] = self.source_run_id
        return result


def parse_release_state(
    *,
    event: str,
    duckdb_version: str,
    duckdb_commit: str,
    status: str,
    client: str | None = None,
    message: str | None = None,
    source_workflow: str | None = None,
    source_run_id: str | None = None,
) -> ReleaseState:
    normalized_event = event.strip()
    normalized_status = status.strip()
    normalized_client = client.strip() if client else None

    if normalized_event not in VALID_EVENTS:
        raise ValueError(f"event must be one of {sorted(VALID_EVENTS)}")
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
    if not duckdb_version.strip():
        raise ValueError("duckdb_version is required")
    if not duckdb_commit.strip():
        raise ValueError("duckdb_commit is required")
    if normalized_event == "client_ready" and not normalized_client:
        raise ValueError("client is required for client_ready")
    if normalized_event == "core_ready" and normalized_client:
        raise ValueError("client must be omitted for core_ready")
    if message is not None and len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"message must be at most {MAX_MESSAGE_LENGTH} characters")

    return ReleaseState(
        event=normalized_event,  # type: ignore[arg-type]
        duckdb_version=duckdb_version.strip(),
        duckdb_commit=duckdb_commit.strip(),
        status=normalized_status,  # type: ignore[arg-type]
        client=normalized_client,
        message=message,
        source_workflow=source_workflow or None,
        source_run_id=source_run_id or None,
    )
