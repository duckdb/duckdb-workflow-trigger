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
hooks:
  # Dispatch after DuckDB core release artifacts are ready.
  # A hook entry can dispatch to one or more downstream workflows.
  core_ready:
    # workflow is owner/repo/workflow.yml@ref. The receiver workflow runs on ref.
    - workflow: duckdb/duckdb-python/release.yml@main
      # inputs are sent exactly as named here to the receiver workflow.
      # Mapping form supports receiver-specific input names, static values,
      # and Python format fields such as {duckdb_commit}.
      inputs:
        duckdb-sha: "{duckdb_commit}"
        pypi-index: prod

  # Dispatch after a specific client release is ready.
  # Group client_ready endpoints by client name so the receiver payload matches
  # the downstream release.
  client_ready:
    python:
      - workflow: duckdb/foo/OnClientReady.yml@main
        # List form forwards same-named release values to the receiver workflow.
        # Available values include duckdb_version, duckdb_commit, payload, event,
        # client, status, and source_run_url.
        inputs:
          - duckdb_version
          - duckdb_commit
          - payload
      - workflow: duckdb/bar/OnClientReady.yml@main
        inputs:
          duckdb-sha: "{duckdb_commit}"
```

To add a downstream workflow, register it under the appropriate hook in
`endpoints.yml`. For `client_ready`, use the client name as the mapping key so
the outbound payload stays aligned with the downstream release.

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
  --duckdb-version v1.2.3 \
  --duckdb-commit 0123456789abcdef0123456789abcdef01234567 \
  --status success
```

The example environment sets `DRY_RUN_GITHUB=true`, so the dispatcher writes
state to MinIO and prints the GitHub workflow dispatch request instead of
calling GitHub. For `client_ready`, add `--client <name>`.
