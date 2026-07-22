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

Endpoints are configured in `endpoints.yml` and grouped by hook. `core_ready`
contains a list of workflow endpoint mappings. `client_ready` is grouped by
client name, and each client contains a list of workflow endpoint mappings.
Each endpoint declares `workflow: owner/repo/workflow.yml@ref` and may declare
`inputs`. Use a list to forward same-named release values, or a mapping for
renamed inputs, static values, and Python format fields such as
`{duckdb_commit}`.

```yaml
hooks:
  core_ready:
    - workflow: duckdb/duckdb-python/release.yml@main
      inputs:
        duckdb-sha: "{duckdb_commit}"
        pypi-index: prod
  client_ready:
    python:
      - workflow: duckdb/foo/OnClientReady.yml@main
        inputs:
          - duckdb_version
          - duckdb_commit
          - payload
      - workflow: duckdb/bar/OnClientReady.yml@main
        inputs:
          duckdb-sha: "{duckdb_commit}"
```

Use `core_ready` for workflows that should run after the DuckDB core release is
ready. Use `client_ready` for workflows that should run after a specific client
release is ready. A hook entry can dispatch to one or more downstream workflows.
Configured `inputs` are sent exactly as defined, including hyphenated input
names, so include every input the downstream workflow expects.

To add a downstream workflow, register it under the appropriate hook in
`endpoints.yml`. For `client_ready`, use the client name as the mapping key so
the outbound payload stays aligned with the downstream release.

### Run the dispatcher locally

Run a dry-run dispatch against the configured endpoints:

```sh
uv run release-dispatcher \
  --event core_ready \
  --duckdb-version v1.2.3 \
  --duckdb-commit 0123456789abcdef0123456789abcdef01234567 \
  --status success
```

For `client_ready`, add `--client <name>`. Set `--dry-run-github` or
`DRY_RUN_GITHUB=true` to print the GitHub workflow dispatch request instead of
calling the GitHub API.

## Development

Release state is written to immutable S3 keys:

- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/core/state.json`
- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/clients/$client/state.json`

Duplicate state writes fail by using S3 create-only semantics. The GitHub
workflow also queues duplicate event/version/client runs with a concurrency
group and `cancel-in-progress: false`.

### Local MinIO setup

Start a local S3-compatible bucket:

```sh
docker compose up -d
```

Load the example environment and run a dry-run dispatch:

```sh
set -a
. ./.env.example
set +a

uv run release-dispatcher \
  --event core_ready \
  --duckdb-version v1.2.3 \
  --duckdb-commit 0123456789abcdef0123456789abcdef01234567 \
  --status success
```

`DRY_RUN_GITHUB=true` writes state to MinIO and prints the GitHub dispatch
request instead of calling GitHub.
