from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from release_dispatcher.config import (
    load_endpoints,
    matching_endpoints,
    registered_client_names,
)
from release_dispatcher.github import GitHubDispatcher
from release_dispatcher.models import parse_release_state
from release_dispatcher.state import S3Settings, S3StateStore, StateAlreadyExistsError


def env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch DuckDB release workflow events")
    parser.add_argument("--event", required=True, choices=["core_ready", "client_ready"])
    parser.add_argument("--duckdb-version", required=True)
    parser.add_argument("--duckdb-commit", required=True)
    parser.add_argument("--status", required=True, choices=["success", "failure", "skipped"])
    parser.add_argument("--client")
    parser.add_argument("--message")
    parser.add_argument("--source-workflow")
    parser.add_argument("--source-run-id")
    parser.add_argument("--endpoint-config", default="endpoints.yml")
    parser.add_argument("--bucket", default=env_value("RELEASE_STATE_BUCKET", "duckdb-release-state"))
    parser.add_argument("--s3-endpoint-url", default=env_value("AWS_ENDPOINT_URL_S3"))
    parser.add_argument("--aws-region", default=env_value("AWS_REGION") or env_value("AWS_DEFAULT_REGION"))
    parser.add_argument("--github-token", default=env_value("PAT_TOKEN") or env_value("GITHUB_TOKEN"))
    parser.add_argument(
        "--dry-run-github",
        action="store_true",
        default=os.getenv("DRY_RUN_GITHUB", "").lower() in {"1", "true", "yes"},
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        state = parse_release_state(
            event=args.event,
            duckdb_version=args.duckdb_version,
            duckdb_commit=args.duckdb_commit,
            status=args.status,
            client=args.client,
            message=args.message,
            source_workflow=args.source_workflow,
            source_run_id=args.source_run_id,
        )
        endpoints = load_endpoints(Path(args.endpoint_config))
    except ValueError as exc:
        parser.error(str(exc))

    if state.event == "client_ready" and state.client not in registered_client_names(endpoints):
        print(f"WARNING: client '{state.client}' is not registered in {args.endpoint_config}", file=sys.stderr)

    store = S3StateStore(
        S3Settings(
            bucket=args.bucket,
            endpoint_url=args.s3_endpoint_url,
            region_name=args.aws_region,
        )
    )
    try:
        key = store.create_state(state)
    except StateAlreadyExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote state to s3://{args.bucket}/{key}")

    if not state.should_dispatch:
        print(f"Stored {state.status} state; skipping outbound dispatch")
        return 0

    if not args.github_token and not args.dry_run_github:
        print("ERROR: PAT_TOKEN or GITHUB_TOKEN is required unless --dry-run-github is set", file=sys.stderr)
        return 1

    dispatcher = GitHubDispatcher(token=args.github_token or "", dry_run=args.dry_run_github)
    endpoints_to_dispatch = matching_endpoints(endpoints, state)
    if not endpoints_to_dispatch:
        print(f"No enabled endpoints registered for hook {state.event}")
        return 0

    for endpoint in endpoints_to_dispatch:
        request = dispatcher.dispatch(endpoint, state)
        print(f"Dispatched {endpoint.name} to {request.url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
