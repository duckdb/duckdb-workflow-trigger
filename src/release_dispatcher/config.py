from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

import yaml

from release_dispatcher.models import ReleaseState


RELEASE_LINE_PATTERN = re.compile(r"^(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?$")
DUCKDB_VERSION_PATTERN = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)(?:[.\-+].+)?$"
)


@dataclass(frozen=True)
class Endpoint:
    name: str
    hook: str
    owner: str
    repo: str
    workflow: str
    ref: str = "main"
    inputs: dict[str, str] | None = None
    release_line: str | None = None

    @property
    def target(self) -> str:
        return f"{self.owner}/{self.repo}/{self.workflow}@{self.ref}"

    @property
    def qualified_name(self) -> str:
        if self.name == self.hook:
            return self.hook
        return f"{self.hook}.{self.name}"

    def dispatch_description(self, state: ReleaseState) -> str:
        release_line = f" (release line {self.release_line})" if self.release_line else ""
        return (
            f"{self.qualified_name} for DuckDB {state.duckdb_version}{release_line} "
            f"to {self.target}"
        )

    def render_inputs(self, state: ReleaseState) -> dict[str, str]:
        if self.inputs is None:
            return {}

        context = _template_context(state)
        return {
            name: _render_template(template, context, f"input {name!r} for endpoint {self.name}")
            for name, template in self.inputs.items()
        }


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
                _endpoints_for_group(
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
        matches = [endpoint for endpoint in matches if endpoint.name == state.client]

    grouped: dict[str, list[Endpoint]] = {}
    for endpoint in matches:
        grouped.setdefault(endpoint.name, []).append(endpoint)

    selected: list[Endpoint] = []
    for name, group in grouped.items():
        unversioned = [endpoint for endpoint in group if endpoint.release_line is None]
        if unversioned:
            selected.extend(unversioned)
            continue

        release_lines = {endpoint.release_line for endpoint in group if endpoint.release_line}
        release_line = _select_release_line(state.duckdb_version, release_lines)
        if release_line is None:
            available = ", ".join(sorted(release_lines, key=_release_line_sort_key))
            raise ValueError(
                f"no release line for DuckDB {state.duckdb_version} in endpoint "
                f"{state.event}.{name}; configured release lines: {available}"
            )
        selected.extend(endpoint for endpoint in group if endpoint.release_line == release_line)
    return selected


def registered_client_names(endpoints: list[Endpoint]) -> set[str]:
    return {
        endpoint.name
        for endpoint in endpoints
        if endpoint.name and endpoint.hook == "client_ready"
    }


def _endpoints_for_group(
    name: str, hook: str, workflow_targets: object, context: str
) -> list[Endpoint]:
    if isinstance(workflow_targets, list):
        return _endpoints_for_targets(name, hook, workflow_targets, context)
    if not isinstance(workflow_targets, dict):
        raise ValueError(
            f"endpoint {context} must be a workflow list or release-line mapping"
        )

    endpoints: list[Endpoint] = []
    for release_line_value, release_targets in workflow_targets.items():
        if not isinstance(release_line_value, str):
            raise ValueError(
                f"release line for endpoint {context} must be a quoted string"
            )
        release_line = release_line_value.strip()
        if not RELEASE_LINE_PATTERN.fullmatch(release_line):
            raise ValueError(
                f"endpoint {context} must be a workflow list or release-line mapping; "
                f"release line {release_line_value!r} must be a quoted major or "
                "major.minor version"
            )
        endpoints.extend(
            _endpoints_for_targets(
                name,
                hook,
                release_targets,
                f"{context}.{release_line}",
                release_line=release_line,
            )
        )
    return endpoints


def _endpoints_for_targets(
    name: str,
    hook: str,
    workflow_targets: object,
    context: str,
    *,
    release_line: str | None = None,
) -> list[Endpoint]:
    if not isinstance(workflow_targets, list):
        raise ValueError(f"endpoint {context} must be a workflow list")

    endpoints: list[Endpoint] = []
    for index, endpoint_config in enumerate(workflow_targets):
        endpoint_context = f"{context}[{index}]"
        if not isinstance(endpoint_config, dict):
            raise ValueError(f"endpoint {endpoint_context} must be a mapping")

        owner, repo, workflow, ref = _parse_workflow_target(
            _non_empty_string(endpoint_config.get("workflow"), f"workflow for {endpoint_context}"),
            endpoint_context,
        )
        endpoints.append(
            Endpoint(
                name=name,
                hook=hook,
                owner=owner,
                repo=repo,
                workflow=workflow,
                ref=ref,
                inputs=_parse_inputs(endpoint_config.get("inputs"), endpoint_context),
                release_line=release_line,
            )
        )
    return endpoints


def _select_release_line(duckdb_version: str, release_lines: set[str]) -> str | None:
    match = DUCKDB_VERSION_PATTERN.fullmatch(duckdb_version.strip())
    if not match:
        raise ValueError(
            f"DuckDB version {duckdb_version!r} must contain a numeric major.minor version"
        )

    major = match.group("major")
    exact = f"{major}.{match.group('minor')}"
    if exact in release_lines:
        return exact
    if major in release_lines:
        return major
    return None


def _release_line_sort_key(release_line: str) -> tuple[int, int]:
    major, separator, minor = release_line.partition(".")
    return int(major), int(minor) if separator else -1


def _parse_inputs(inputs: object, context: str) -> dict[str, str] | None:
    if inputs is None:
        return None
    if isinstance(inputs, list):
        return _parse_input_names(inputs, context)
    if not isinstance(inputs, dict):
        raise ValueError(f"endpoint {context} inputs must be a mapping or list")

    parsed: dict[str, str] = {}
    for key, value in inputs.items():
        input_name = _non_empty_string(key, f"input name for {context}")
        if isinstance(value, (dict, list)):
            raise ValueError(f"input {input_name!r} for endpoint {context} must be a scalar value")
        parsed[input_name] = "" if value is None else str(value)
    return parsed


def _parse_input_names(inputs: list[object], context: str) -> dict[str, str]:
    context_values = set(_template_context_values())
    parsed: dict[str, str] = {}
    for index, value in enumerate(inputs):
        input_name = _non_empty_string(value, f"input name for {context}[{index}]")
        if input_name not in context_values:
            raise ValueError(
                f"input name {input_name!r} for endpoint {context} must be a known template value"
            )
        parsed[input_name] = f"{{{input_name}}}"
    return parsed


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


def _template_context(state: ReleaseState) -> dict[str, str]:
    import json

    context = dict.fromkeys(_template_context_values(), "")
    context.update(
        {
            "duckdb_version": state.duckdb_version,
            "duckdb_commit": state.duckdb_commit,
            "event": state.event,
            "client": state.client or "",
            "status": state.status,
            "source_run_url": state.source_run_url or "",
            "payload": json.dumps(state.outbound_payload, sort_keys=True),
        }
    )
    return context


def _template_context_values() -> tuple[str, ...]:
    return (
        "duckdb_version",
        "duckdb_commit",
        "event",
        "client",
        "status",
        "source_run_url",
        "payload",
    )


def _render_template(template: str, context: dict[str, str], description: str) -> str:
    try:
        fields = list(Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"{description} is not a valid format template: {exc}") from exc

    for _, field_name, _, _ in fields:
        if field_name is None:
            continue
        if field_name not in context:
            raise ValueError(f"{description} references unknown template value {field_name!r}")

    try:
        return template.format_map(context)
    except ValueError as exc:
        raise ValueError(f"{description} is not a valid format template: {exc}") from exc
