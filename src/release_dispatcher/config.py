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
        if isinstance(hook_endpoints, list):
            endpoints.extend(_endpoints_for_targets(hook_name, hook_name, hook_endpoints, hook_name))
            continue
        if not isinstance(hook_endpoints, dict):
            raise ValueError(f"hook {hook_name} must contain a workflow list or endpoint mapping")
        for name, workflow_targets in hook_endpoints.items():
            endpoint_name = _non_empty_string(name, f"endpoint name for hook {hook_name}")
            endpoints.extend(
                _endpoints_for_targets(
                    endpoint_name,
                    hook_name,
                    workflow_targets,
                    f"{hook_name}.{endpoint_name}",
                )
            )
    return endpoints


def matching_endpoints(endpoints: list[Endpoint], state: ReleaseState) -> list[Endpoint]:
    matches = [endpoint for endpoint in endpoints if endpoint.hook == state.event]
    if state.event == "client_ready":
        return [endpoint for endpoint in matches if endpoint.name == state.client]
    return matches


def registered_client_names(endpoints: list[Endpoint]) -> set[str]:
    return {
        endpoint.name
        for endpoint in endpoints
        if endpoint.name and endpoint.hook == "client_ready"
    }


def _endpoints_for_targets(name: str, hook: str, workflow_targets: object, context: str) -> list[Endpoint]:
    if not isinstance(workflow_targets, list):
        raise ValueError(f"endpoint {context} must be a workflow list")

    endpoints: list[Endpoint] = []
    for index, workflow_target in enumerate(workflow_targets):
        owner, repo, workflow, ref = _parse_workflow_target(
            _non_empty_string(workflow_target, f"workflow for {context}[{index}]"),
            f"{context}[{index}]",
        )
        endpoints.append(
            Endpoint(
                name=name,
                hook=hook,
                owner=owner,
                repo=repo,
                workflow=workflow,
                ref=ref,
            )
        )
    return endpoints


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
