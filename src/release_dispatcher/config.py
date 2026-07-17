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
            for workflow_target, context in _workflow_targets(raw_endpoint, f"{hook_name}.{endpoint_name}"):
                owner, repo, workflow, ref = _parse_workflow_target(
                    workflow_target,
                    context,
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
    matches = [endpoint for endpoint in endpoints if endpoint.hook == state.event]
    if state.event == "client_ready":
        return [endpoint for endpoint in matches if endpoint.name == state.client]
    return matches


def registered_client_names(endpoints: list[Endpoint]) -> set[str]:
    return {
        endpoint.name
        for endpoint in endpoints
        if endpoint.name and endpoint.hook in {"core_ready", "client_ready"}
    }


def _workflow_targets(raw_endpoint: dict, context: str) -> list[tuple[str, str]]:
    workflow_targets = raw_endpoint.get("workflows")
    if "workflow" in raw_endpoint:
        raise ValueError(f"endpoint {context} must use workflows")
    if workflow_targets:
        if not isinstance(workflow_targets, list):
            raise ValueError(f"endpoint {context} workflows must be a list")
        return [
            (_non_empty_string(target, f"workflow for {context}[{index}]"), f"{context}[{index}]")
            for index, target in enumerate(workflow_targets)
        ]
    raise ValueError(f"endpoint {context} is missing workflows")


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
