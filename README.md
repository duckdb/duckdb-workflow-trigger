# DuckDB Workflow Trigger

This repository contains the existing nightly workflow trigger and a release event
dispatcher for DuckDB release state.

## Usage

The release dispatcher accepts `core_ready` and `client_ready` workflow dispatch
events, creates an immutable state file in S3, and dispatches successful events
to registered downstream repository workflows.

Downstream workflows receive the inputs configured for their endpoint. The
default DuckDB release values available to endpoint templates are:

- `duckdb_version`
- `duckdb_commit`
- `payload`, for example `{"phase":"core_ready"}` or
  `{"phase":"client_ready","name":"python"}`
- `event`
- `client`
- `status`
- `source_run_url`

### Configure endpoints

Endpoints are configured in `endpoints.yml` and grouped by hook.

```yaml
defaults:
  # Endpoints inherit these inputs when they do not define their own inputs.
  inputs:
    duckdb-sha: "{duckdb_commit}"
    duckdb-version: "{duckdb_version}"

hooks:
  # Dispatch after DuckDB core release artifacts are ready.
  # Group endpoints by downstream integration, then by DuckDB release line.
  core_ready:
    python:
      # An exact major.minor release line takes precedence over the major fallback.
      "2.0":
        # workflow is owner/repo/workflow.yml@ref. The receiver runs at this ref.
        - workflow: duckdb/duckdb-python/release.yml@v2.0-cyanoptera
          # Explicit inputs replace the defaults, so include the defaults again
          # when adding receiver-specific values.
          inputs:
            duckdb-sha: "{duckdb_commit}"
            duckdb-version: "{duckdb_version}"
            pypi-index: prod
      # A major release line matches other releases in that major version.
      "2":
        - workflow: duckdb/duckdb-python/release.yml@main
          inputs:
            duckdb-sha: "{duckdb_commit}"
            duckdb-version: "{duckdb_version}"
            pypi-index: prod

    java:
      "2":
        - workflow: duckdb/duckdb-java/Vendor.yml@main

  # Dispatch after a specific client release is ready.
  # Group endpoints by client name so the payload matches the downstream release.
  client_ready:
    r:
      "2":
        - workflow: duckdb/duckdb-r/OnClientReady.yml@main
          # List form replaces the defaults and forwards same-named values.
          inputs:
            - duckdb_version
            - duckdb_commit
            - payload
```

Each downstream name contains its release-line routes. An exact `major.minor`
route wins over the `major` fallback, so `v2.0.7` uses `"2.0"` while `v2.1.0`
uses `"2"`. A major route matches only that major version. Release-line keys
must be quoted so YAML treats them as strings. If a successful event has no
route for an applicable downstream, dispatch fails before its immutable state
is written.

An endpoint that omits `inputs` inherits `defaults.inputs`. Any explicit input
mapping or list replaces the defaults instead of merging with them. Use
`inputs: null` or an empty list to send no inputs. If `defaults` is omitted,
endpoints without inputs retain the legacy empty-input behavior.

`workflow` uses `owner/repo/workflow.yml@ref`; the receiver workflow runs at
that ref. Mapping-form inputs support receiver-specific names, static values,
and format fields such as `{duckdb_commit}`. List-form inputs forward the
same-named release values. The original full DuckDB version is used for input
rendering even though routing only considers its major and minor components.

The legacy unversioned workflow-list forms remain supported. For
`client_ready`, the downstream name must still match the event's client name.
Dispatch logs include the selected release line and the complete workflow
target, for example:

```text
Dispatched core_ready.python for DuckDB v2.0.7 (release line 2.0) to duckdb/duckdb-python/release.yml@v2.0-cyanoptera
```

## Development

Release state is written to immutable S3 keys:

- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/core/state.json`
- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/clients/$client/state.json`

Duplicate state writes fail by using S3 create-only semantics. The GitHub
workflow also queues duplicate event/version/client runs with a concurrency
group and `cancel-in-progress: false`.

### Local dispatcher setup

Start a local S3-compatible bucket, load the example environment, and run a
dry-run dispatch against the configured endpoints:

```sh
docker compose up -d

set -a
. ./.env.example
set +a

uv run release-dispatcher \
  --event core_ready \
  --duckdb-version v2.1.0 \
  --duckdb-commit 0123456789abcdef0123456789abcdef01234567 \
  --status success
```

The example environment sets `DRY_RUN_GITHUB=true`, so the dispatcher writes
state to MinIO and prints the GitHub workflow dispatch request instead of
calling GitHub. For `client_ready`, add `--client <name>`.
