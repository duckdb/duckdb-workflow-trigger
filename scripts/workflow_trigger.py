"""Plan and dispatch scheduled or manually requested DuckDB CI workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RELEASE_BRANCH = re.compile(r"^v[1-9][0-9]*\.[0-9]+-")
LEGACY_CI_BRANCH = re.compile(r"^v1\.[0-5]-")
RECENT_SECONDS = 48 * 60 * 60


@dataclass(frozen=True)
class RunConfig:
    scheduled: bool
    nightly: bool
    needs_upstream: bool
    skip_tests: bool


# Cron expressions identify the intended slot even when GitHub queues the run.
# Runs without tests warm the CI caches.
SCHEDULES = {
    "50 2 * * *": RunConfig(scheduled=True, nightly=True, needs_upstream=True, skip_tests=False),
    "50 9 * * 1-5": RunConfig(scheduled=True, nightly=False, needs_upstream=False, skip_tests=True),
    "50 11 * * 1-5": RunConfig(scheduled=True, nightly=False, needs_upstream=True, skip_tests=True),
    "50 13 * * 1-5": RunConfig(
        scheduled=True, nightly=False, needs_upstream=False, skip_tests=False
    ),
    "50 15 * * 1-5": RunConfig(
        scheduled=True, nightly=False, needs_upstream=False, skip_tests=True
    ),
}


@dataclass(frozen=True)
class WorkflowDispatch:
    repository: str
    workflow: str
    branch: str
    inputs: dict[str, str] = field(default_factory=dict)

    def payload(self) -> dict[str, str | dict[str, str]]:
        payload: dict[str, str | dict[str, str]] = {"ref": f"refs/heads/{self.branch}"}
        if self.inputs:
            payload["inputs"] = self.inputs
        return payload


def event_config(
    event_name: str,
    schedule: str = "",
    *,
    trigger_nightly: bool = False,
    skip_tests: bool = False,
) -> RunConfig:
    if event_name == "schedule":
        if schedule not in SCHEDULES:
            raise ValueError(f"Unknown schedule: {schedule!r}")
        return SCHEDULES[schedule]
    if event_name == "workflow_dispatch":
        return RunConfig(
            scheduled=False,
            nightly=trigger_nightly,
            needs_upstream=trigger_nightly,
            skip_tests=skip_tests,
        )
    raise ValueError(f"Unsupported event: {event_name!r}")


def recent_branches(
    branch_tips: Mapping[str, int], now: datetime, *, include_main: bool = False
) -> list[str]:
    cutoff = int(now.timestamp()) - RECENT_SECONDS
    return sorted(
        branch
        for branch, timestamp in branch_tips.items()
        if (RELEASE_BRANCH.match(branch) or (include_main and branch == "main"))
        and timestamp >= cutoff
    )


def build_dispatches(
    config: RunConfig,
    branch_tips: Mapping[str, int],
    now: datetime,
    *,
    duckdb_ref: str = "",
) -> list[WorkflowDispatch]:
    if not config.scheduled and not config.nightly:
        return [
            WorkflowDispatch(
                "duckdb",
                "Wasm.yml",
                "main",
                {"release_s3": "true", "duckdb-ref": duckdb_ref},
            )
        ]

    branches = (
        recent_branches(branch_tips, now, include_main=not config.scheduled)
        if config.needs_upstream
        else []
    )
    if config.scheduled:
        branches.insert(0, "main")

    dispatches = []
    for branch in branches:
        if config.nightly:
            dispatches.append(WorkflowDispatch("duckdb", "NightlyTests.yml", branch))
        dispatches.append(
            WorkflowDispatch(
                "duckdb", "Main.yml", branch, {"skip_tests": str(config.skip_tests).lower()}
            )
        )
        if config.nightly and LEGACY_CI_BRANCH.match(branch):
            dispatches.append(
                WorkflowDispatch(
                    "duckdb",
                    "InvokeCI.yml",
                    branch,
                    {
                        "skip_tests": "false",
                        "git_ref": branch,
                        "run_all": "true",
                        "twine_upload": "true",
                    },
                )
            )

    if config.nightly:
        dispatches.extend(
            [
                WorkflowDispatch("duckdb", "IssuesCloseStale.yml", "main"),
                WorkflowDispatch("ducklake", "MainDistributionPipeline.yml", "v1.4-andium"),
            ]
        )
    return dispatches


def read_branch_tips(repo_dir: Path) -> dict[str, int]:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "fetch",
            "--prune",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        ],
        check=True,
    )
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "for-each-ref",
            "--format=%(refname) %(committerdate:unix)",
            "refs/remotes/origin",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    branch_tips = {}
    for line in result.stdout.splitlines():
        ref, timestamp = line.rsplit(" ", 1)
        branch_tips[ref.removeprefix("refs/remotes/origin/")] = int(timestamp)
    return branch_tips


def dispatch_workflows(
    dispatches: Sequence[WorkflowDispatch], trigger_script: Path = Path("trigger.sh")
) -> None:
    for dispatch in dispatches:
        print(
            f"Dispatching {dispatch.workflow} for {dispatch.repository}:{dispatch.branch}",
            flush=True,
        )
        subprocess.run(
            [
                str(trigger_script.resolve()),
                dispatch.repository,
                json.dumps(dispatch.payload()),
                dispatch.workflow,
            ],
            check=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["config", "dispatch"])
    parser.add_argument("--repo-dir", type=Path, default=Path("duckdb-upstream"))
    args = parser.parse_args(argv)

    try:
        config = event_config(
            os.getenv("EVENT_NAME", ""),
            os.getenv("EVENT_SCHEDULE", ""),
            trigger_nightly=os.getenv("TRIGGER_NIGHTLY", "").lower() == "true",
            skip_tests=os.getenv("SKIP_TESTS", "").lower() == "true",
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.command == "config":
        output = f"needs_upstream={str(config.needs_upstream).lower()}\n"
        if output_path := os.getenv("GITHUB_OUTPUT"):
            with Path(output_path).open("a", encoding="utf-8") as output_file:
                output_file.write(output)
        else:
            print(output, end="")
        return 0

    branch_tips = read_branch_tips(args.repo_dir) if config.needs_upstream else {}
    dispatches = build_dispatches(
        config, branch_tips, datetime.now(timezone.utc), duckdb_ref=os.getenv("DUCKDB_REF", "")
    )
    dispatch_workflows(dispatches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
