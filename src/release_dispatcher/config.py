from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from release_dispatcher.models import ReleaseState


@dataclass(frozen=True)
class Endpoint:
    name: str
    hook: str
    owner: str
    repo: str
    workflow: str
    ref: str = "main"
    enabled: bool = True


def load_endpoints(path: Path) -> list[Endpoint]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    endpoints_data = data.get("endpoints")
    if not isinstance(endpoints_data, list):
        raise ValueError("endpoint config must contain an endpoints list")

    endpoints: list[Endpoint] = []
    for index, raw in enumerate(endpoints_data):
        if not isinstance(raw, dict):
            raise ValueError(f"endpoint {index} must be a mapping")
        endpoints.append(_parse_endpoint(raw, index))
    return endpoints


def matching_endpoints(endpoints: list[Endpoint], state: ReleaseState) -> list[Endpoint]:
    return [
        endpoint
        for endpoint in endpoints
        if endpoint.enabled and endpoint.hook == state.event
    ]


def registered_client_names(endpoints: list[Endpoint]) -> set[str]:
    return {
        endpoint.name
        for endpoint in endpoints
        if endpoint.enabled and endpoint.name and endpoint.hook in {"core_ready", "client_ready"}
    }


def _parse_endpoint(raw: dict[str, Any], index: int) -> Endpoint:
    required = ["name", "hook", "owner", "repo", "workflow"]
    missing = [field for field in required if not raw.get(field)]
    if missing:
        raise ValueError(f"endpoint {index} is missing required field(s): {', '.join(missing)}")

    return Endpoint(
        name=str(raw["name"]),
        hook=str(raw["hook"]),
        owner=str(raw["owner"]),
        repo=str(raw["repo"]),
        workflow=str(raw["workflow"]),
        ref=str(raw.get("ref") or "main"),
        enabled=bool(raw.get("enabled", True)),
    )
