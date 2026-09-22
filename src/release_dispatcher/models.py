from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


ReleaseEvent = Literal["core_ready", "client_ready", "check"]
ReleaseStatus = Literal["success", "failure", "skipped"]

VALID_EVENTS: set[str] = {"core_ready", "client_ready", "check"}
VALID_STATUSES: set[str] = {"success", "failure", "skipped"}
MAX_MESSAGE_LENGTH = 1000


@dataclass(frozen=True)
class ReleaseState:
    event: ReleaseEvent
    duckdb_version: str
    duckdb_commit: str
    status: ReleaseStatus
    name: str | None = None
    message: str | None = None
    source_run_url: str | None = None

    @property
    def should_dispatch(self) -> bool:
        return self.status == "success"

    @property
    def state_key(self) -> str:
        if self.event == "core_ready":
            return f"{self.duckdb_version}/core/state.json"
        if not self.name:
            raise ValueError(f"name is required for {self.event} state paths")
        if self.event == "client_ready":
            return f"{self.duckdb_version}/clients/{self.name}/state.json"
        return f"{self.duckdb_version}/checks/{self.name}/state.json"

    @property
    def outbound_payload(self) -> dict[str, str]:
        if self.event == "core_ready":
            return {"phase": "core_ready"}
        if not self.name:
            raise ValueError(f"name is required for {self.event} payloads")
        return {"phase": self.event, "name": self.name}

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "event": self.event,
            "duckdb_version": self.duckdb_version,
            "duckdb_commit": self.duckdb_commit,
            "status": self.status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.name is not None:
            result["name"] = self.name
        if self.message:
            result["message"] = self.message
        if self.source_run_url:
            result["source_run_url"] = self.source_run_url
        return result


def parse_release_state(
    *,
    event: str,
    duckdb_version: str,
    duckdb_commit: str,
    status: str,
    name: str | None = None,
    client: str | None = None,
    message: str | None = None,
    source_run_url: str | None = None,
) -> ReleaseState:
    normalized_event = event.strip()
    normalized_status = status.strip()
    normalized_name = name.strip() if name else None
    normalized_client = client.strip() if client else None

    if normalized_event not in VALID_EVENTS:
        raise ValueError(f"event must be one of {sorted(VALID_EVENTS)}")
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
    if not duckdb_version.strip():
        raise ValueError("duckdb_version is required")
    if not duckdb_commit.strip():
        raise ValueError("duckdb_commit is required")
    if normalized_event == "core_ready" and (normalized_name or normalized_client):
        raise ValueError("name and client must be omitted for core_ready")
    if normalized_event == "client_ready":
        if normalized_name and normalized_client and normalized_name != normalized_client:
            raise ValueError("name and client must match when both are provided")
        normalized_name = normalized_name or normalized_client
        if not normalized_name:
            raise ValueError("name or client is required for client_ready")
    if normalized_event == "check":
        if normalized_client:
            raise ValueError("client must be omitted for check")
        if not normalized_name:
            raise ValueError("name is required for check")
    if message is not None and len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"message must be at most {MAX_MESSAGE_LENGTH} characters")

    return ReleaseState(
        event=normalized_event,  # type: ignore[arg-type]
        duckdb_version=duckdb_version.strip(),
        duckdb_commit=duckdb_commit.strip(),
        status=normalized_status,  # type: ignore[arg-type]
        name=normalized_name,
        message=message,
        source_run_url=source_run_url or None,
    )
