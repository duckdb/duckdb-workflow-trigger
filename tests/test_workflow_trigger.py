import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import workflow_trigger as trigger

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
NOW_EPOCH = int(NOW.timestamp())
SLOTS = [
    ("50 2 * * *", False, True, True),
    ("50 9 * * 1-5", True, False, False),
    ("50 11 * * 1-5", True, True, False),
    ("50 13 * * 1-5", False, False, False),
    ("50 15 * * 1-5", True, False, False),
]


def test_workflow_declares_amsterdam_schedule_and_conditional_checkout():
    workflow = yaml.load(
        Path(".github/workflows/Workflow-Trigger.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert workflow["on"]["schedule"] == [
        {"cron": cron, "timezone": "Europe/Amsterdam"} for cron, *_ in SLOTS
    ]
    checkout = next(
        step
        for step in workflow["jobs"]["build-linux"]["steps"]
        if step.get("with", {}).get("repository") == "duckdb/duckdb"
    )
    assert checkout["if"] == "${{ fromJSON(steps.config.outputs.needs_upstream) }}"


@pytest.mark.parametrize("cron,skip_tests,needs_upstream,nightly", SLOTS)
def test_scheduled_dispatches(cron, skip_tests, needs_upstream, nightly):
    config = trigger.event_config(
        "schedule",
        cron,
        # Scheduled runs must ignore manual settings.
        trigger_nightly=not nightly,
        skip_tests=not skip_tests,
    )
    branch_tips = {
        "main": NOW_EPOCH - 72 * 3600,
        "v2.0-cyanoptera": NOW_EPOCH - 3600,
        "v1.4-andium": NOW_EPOCH - 2 * 3600,
        "v1.5-variegata": NOW_EPOCH - 72 * 3600,
        "feature": NOW_EPOCH,
    }

    assert config.needs_upstream is needs_upstream
    dispatches = trigger.build_dispatches(config, branch_tips, NOW)
    main_runs = [dispatch for dispatch in dispatches if dispatch.workflow == "Main.yml"]
    expected_branches = {"main", "v2.0-cyanoptera", "v1.4-andium"} if needs_upstream else {"main"}
    assert {dispatch.branch for dispatch in main_runs} == expected_branches
    assert len(main_runs) == len(expected_branches)
    assert all(dispatch.inputs == {"skip_tests": str(skip_tests).lower()} for dispatch in main_runs)

    nightly_runs = {
        dispatch.branch for dispatch in dispatches if dispatch.workflow == "NightlyTests.yml"
    }
    assert nightly_runs == (expected_branches if nightly else set())
    assert any(dispatch.workflow == "InvokeCI.yml" for dispatch in dispatches) is nightly
    assert any(dispatch.workflow == "IssuesCloseStale.yml" for dispatch in dispatches) is nightly
    assert (
        any(
            dispatch.repository == "ducklake"
            and dispatch.workflow == "MainDistributionPipeline.yml"
            for dispatch in dispatches
        )
        is nightly
    )


@pytest.mark.parametrize("branch", ["v2.0-cyanoptera", "v1.4-andium"])
@pytest.mark.parametrize("offset,eligible", [(-1, False), (0, True), (1, True)])
def test_release_branch_cutoff_is_inclusive(branch, offset, eligible):
    tip = NOW_EPOCH - 48 * 3600 + offset
    branches = trigger.recent_branches({branch: tip}, NOW)

    assert branches == ([branch] if eligible else [])


def test_only_eligible_release_branches_are_selected():
    tips = dict.fromkeys(
        [
            "main",
            "HEAD",
            "feature",
            "v0.1-example",
            "v1.4",
            "v1.4-andium",
            "v2.0-cyanoptera",
            "v10.12-example",
        ],
        NOW_EPOCH,
    )

    assert trigger.recent_branches(tips, NOW) == [
        "v1.4-andium",
        "v10.12-example",
        "v2.0-cyanoptera",
    ]


@pytest.mark.parametrize("cron", ["50 2 * * *", "50 11 * * 1-5"])
def test_unchanged_release_branches_are_skipped_but_main_is_always_scheduled(cron):
    config = trigger.event_config("schedule", cron)
    tips = {"main": NOW_EPOCH, "v2.0-cyanoptera": NOW_EPOCH - 48 * 3600 - 1}

    dispatches = trigger.build_dispatches(config, tips, NOW)
    main_runs = [dispatch for dispatch in dispatches if dispatch.workflow == "Main.yml"]

    assert [dispatch.branch for dispatch in main_runs] == ["main"]
    assert not any(dispatch.branch == "v2.0-cyanoptera" for dispatch in dispatches)


@pytest.mark.parametrize("skip_tests", [False, True])
@pytest.mark.parametrize("main_changed", [False, True])
def test_manual_nightly_retains_change_gate_and_skip_tests(skip_tests, main_changed):
    config = trigger.event_config("workflow_dispatch", trigger_nightly=True, skip_tests=skip_tests)
    tips = {
        "main": NOW_EPOCH if main_changed else NOW_EPOCH - 72 * 3600,
        "v2.0-cyanoptera": NOW_EPOCH,
    }

    assert config.needs_upstream is True
    dispatches = trigger.build_dispatches(config, tips, NOW)
    expected_branches = {"main", "v2.0-cyanoptera"} if main_changed else {"v2.0-cyanoptera"}
    main_runs = [dispatch for dispatch in dispatches if dispatch.workflow == "Main.yml"]
    assert {dispatch.branch for dispatch in main_runs} == expected_branches
    assert all(dispatch.inputs == {"skip_tests": str(skip_tests).lower()} for dispatch in main_runs)
    assert {
        dispatch.branch for dispatch in dispatches if dispatch.workflow == "NightlyTests.yml"
    } == expected_branches


def test_manual_nightly_without_changes_still_dispatches_maintenance():
    config = trigger.event_config("workflow_dispatch", trigger_nightly=True)

    assert trigger.build_dispatches(config, {}, NOW) == [
        trigger.WorkflowDispatch("duckdb", "IssuesCloseStale.yml", "main"),
        trigger.WorkflowDispatch("ducklake", "MainDistributionPipeline.yml", "v1.4-andium"),
    ]


def test_legacy_ci_is_nightly_only_and_preserves_its_inputs():
    tips = dict.fromkeys(
        ["v1.0-anatina", "v1.5-variegata", "v1.6-example", "v2.0-cyanoptera"], NOW_EPOCH
    )
    config = trigger.event_config("workflow_dispatch", trigger_nightly=True, skip_tests=True)

    dispatches = trigger.build_dispatches(config, tips, NOW)
    legacy_runs = [dispatch for dispatch in dispatches if dispatch.workflow == "InvokeCI.yml"]

    assert {dispatch.branch for dispatch in legacy_runs} == {"v1.0-anatina", "v1.5-variegata"}
    for dispatch in legacy_runs:
        assert dispatch.payload() == {
            "ref": f"refs/heads/{dispatch.branch}",
            "inputs": {
                "skip_tests": "false",
                "git_ref": dispatch.branch,
                "run_all": "true",
                "twine_upload": "true",
            },
        }


def test_manual_wasm_preserves_ref_without_needing_upstream():
    config = trigger.event_config("workflow_dispatch", trigger_nightly=False)
    duckdb_ref = 'refs/pull/123/head"$(literal)'

    assert config.needs_upstream is False
    assert trigger.build_dispatches(config, {}, NOW, duckdb_ref=duckdb_ref) == [
        trigger.WorkflowDispatch(
            "duckdb", "Wasm.yml", "main", {"release_s3": "true", "duckdb-ref": duckdb_ref}
        )
    ]


@pytest.mark.parametrize(
    "event,schedule", [("schedule", "unknown"), ("schedule", ""), ("push", "")]
)
def test_unexpected_events_fail_instead_of_dispatching(event, schedule):
    with pytest.raises(ValueError):
        trigger.event_config(event, schedule)


def test_git_discovery_fetches_all_branches_and_reads_committer_timestamps(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            stdout=(
                f"refs/remotes/origin/main {NOW_EPOCH}\n"
                f"refs/remotes/origin/v2.0-cyanoptera {NOW_EPOCH - 3600}\n"
            )
        )

    monkeypatch.setattr(trigger.subprocess, "run", run)

    assert trigger.read_branch_tips(Path("upstream")) == {
        "main": NOW_EPOCH,
        "v2.0-cyanoptera": NOW_EPOCH - 3600,
    }
    assert calls == [
        (
            [
                "git",
                "-C",
                "upstream",
                "fetch",
                "--prune",
                "origin",
                "+refs/heads/*:refs/remotes/origin/*",
            ],
            {"check": True},
        ),
        (
            [
                "git",
                "-C",
                "upstream",
                "for-each-ref",
                "--format=%(refname) %(committerdate:unix)",
                "refs/remotes/origin",
            ],
            {"check": True, "capture_output": True, "text": True},
        ),
    ]


def test_git_failure_stops_branch_discovery(monkeypatch):
    def run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(trigger.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        trigger.read_branch_tips(Path("upstream"))


def test_dispatch_serializes_json_as_one_argument_without_a_shell(monkeypatch, tmp_path):
    calls = []
    dispatch = trigger.WorkflowDispatch(
        "duckdb", "Wasm.yml", "main", {"duckdb-ref": 'branch"$(literal)'}
    )

    def run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(trigger.subprocess, "run", run)
    script = tmp_path / "trigger.sh"
    trigger.dispatch_workflows([dispatch], script)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == str(script)
    assert args[1] == "duckdb"
    assert json.loads(args[2]) == dispatch.payload()
    assert args[3] == "Wasm.yml"
    assert kwargs == {"check": True}


def test_dispatch_failure_stops_remaining_dispatches(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(trigger.subprocess, "run", run)
    dispatches = [
        trigger.WorkflowDispatch("duckdb", "Main.yml", "main"),
        trigger.WorkflowDispatch("duckdb", "Main.yml", "v2.0-cyanoptera"),
    ]

    with pytest.raises(subprocess.CalledProcessError):
        trigger.dispatch_workflows(dispatches)
    assert len(calls) == 1


@pytest.fixture
def event_env(monkeypatch):
    for name in (
        "EVENT_NAME",
        "EVENT_SCHEDULE",
        "TRIGGER_NIGHTLY",
        "SKIP_TESTS",
        "DUCKDB_REF",
        "GITHUB_OUTPUT",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("cron,skip_tests,needs_upstream,nightly", SLOTS)
def test_config_command_appends_checkout_output_without_git(
    event_env, tmp_path, cron, skip_tests, needs_upstream, nightly
):
    output = tmp_path / "github-output"
    output.write_text("existing=value\n", encoding="utf-8")
    event_env.setenv("EVENT_NAME", "schedule")
    event_env.setenv("EVENT_SCHEDULE", cron)
    event_env.setenv("GITHUB_OUTPUT", str(output))

    def unexpected_read(repo_dir):
        pytest.fail("Config must not read upstream branches")

    event_env.setattr(trigger, "read_branch_tips", unexpected_read)

    assert trigger.main(["config"]) == 0
    assert output.read_text(encoding="utf-8") == (
        f"existing=value\nneeds_upstream={str(needs_upstream).lower()}\n"
    )


@pytest.mark.parametrize("cron,reads_upstream", [("50 11 * * 1-5", True), ("50 13 * * 1-5", False)])
def test_dispatch_command_only_reads_upstream_when_needed(event_env, cron, reads_upstream):
    event_env.setenv("EVENT_NAME", "schedule")
    event_env.setenv("EVENT_SCHEDULE", cron)
    read_calls = []
    dispatched = []

    def read(repo_dir):
        read_calls.append(repo_dir)
        return {}

    event_env.setattr(trigger, "read_branch_tips", read)
    event_env.setattr(trigger, "dispatch_workflows", dispatched.extend)

    assert trigger.main(["dispatch", "--repo-dir", "upstream"]) == 0
    assert read_calls == ([Path("upstream")] if reads_upstream else [])
    assert [dispatch.workflow for dispatch in dispatched] == ["Main.yml"]
    assert dispatched[0].branch == "main"


def test_manual_command_forwards_wasm_ref_from_environment(event_env):
    event_env.setenv("EVENT_NAME", "workflow_dispatch")
    event_env.setenv("TRIGGER_NIGHTLY", "false")
    event_env.setenv("DUCKDB_REF", "refs/pull/123/head")
    dispatched = []

    def unexpected_read(repo_dir):
        pytest.fail("WASM dispatch must not read upstream branches")

    event_env.setattr(trigger, "read_branch_tips", unexpected_read)
    event_env.setattr(trigger, "dispatch_workflows", dispatched.extend)

    assert trigger.main(["dispatch"]) == 0
    assert dispatched[0].payload() == {
        "ref": "refs/heads/main",
        "inputs": {"release_s3": "true", "duckdb-ref": "refs/pull/123/head"},
    }


def test_manual_nightly_command_reads_boolean_inputs_from_environment(event_env):
    event_env.setenv("EVENT_NAME", "workflow_dispatch")
    event_env.setenv("TRIGGER_NIGHTLY", "true")
    event_env.setenv("SKIP_TESTS", "true")
    dispatched = []
    event_env.setattr(
        trigger,
        "read_branch_tips",
        lambda repo_dir: {"main": int(datetime.now(timezone.utc).timestamp())},
    )
    event_env.setattr(trigger, "dispatch_workflows", dispatched.extend)

    assert trigger.main(["dispatch"]) == 0
    assert [dispatch.workflow for dispatch in dispatched] == [
        "NightlyTests.yml",
        "Main.yml",
        "IssuesCloseStale.yml",
        "MainDistributionPipeline.yml",
    ]
    assert dispatched[1].inputs == {"skip_tests": "true"}
