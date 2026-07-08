from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def load_endpoints(path: Path) -> list[Endpoint]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        raise ValueError("endpoint config must contain a hooks mapping")

    endpoints: list[Endpoint] = []
    for hook, hook_endpoints in hooks.items():
        hook_name = _non_empty_string(hook, "hook name")
        if not isinstance(hook_endpoints, dict):
            raise ValueError(f"hook {hook_name} must contain an endpoint mapping")
        for name, raw_endpoint in hook_endpoints.items():
            endpoint_name = _non_empty_string(name, f"endpoint name for hook {hook_name}")
            if not isinstance(raw_endpoint, dict):
                raise ValueError(f"endpoint {hook_name}.{endpoint_name} must be a mapping")
            workflow_target = raw_endpoint.get("workflow")
            if not workflow_target:
                raise ValueError(f"endpoint {hook_name}.{endpoint_name} is missing workflow")
            owner, repo, workflow, ref = _parse_workflow_target(
                _non_empty_string(workflow_target, f"workflow for {hook_name}.{endpoint_name}"),
                f"{hook_name}.{endpoint_name}",
            )
            endpoints.append(
                Endpoint(
                    name=endpoint_name,
                    hook=hook_name,
                    owner=owner,
                    repo=repo,
                    workflow=workflow,
                    ref=ref,
                )
            )
    return endpoints


def matching_endpoints(endpoints: list[Endpoint], state: ReleaseState) -> list[Endpoint]:
    return [endpoint for endpoint in endpoints if endpoint.hook == state.event]


def registered_client_names(endpoints: list[Endpoint]) -> set[str]:
    return {
        endpoint.name
        for endpoint in endpoints
        if endpoint.name and endpoint.hook in {"core_ready", "client_ready"}
    }


def _parse_workflow_target(target: str, context: str) -> tuple[str, str, str, str]:
    workflow_path, separator, ref = target.rpartition("@")
    if not separator:
        raise ValueError(f"endpoint {context} workflow must include @ref")

    parts = workflow_path.split("/")
    if len(parts) != 3:
        raise ValueError(f"endpoint {context} workflow must be owner/repo/workflow.yml@ref")

    owner, repo, workflow = parts
    return (
        _non_empty_string(owner, f"owner for {context}"),
        _non_empty_string(repo, f"repo for {context}"),
        _non_empty_string(workflow, f"workflow for {context}"),
        _non_empty_string(ref, f"ref for {context}"),
    )


def _non_empty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value.strip()
