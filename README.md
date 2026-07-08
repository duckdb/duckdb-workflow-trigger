# DuckDB Workflow Trigger

This repository contains the existing nightly workflow trigger and a release event
dispatcher for DuckDB release state.

## Release Dispatch

The release dispatcher accepts `core_ready` and `client_ready` workflow dispatch
events, creates an immutable state file in S3, and dispatches successful events
to registered downstream repository workflows.

State is written to:

- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/core/state.json`
- `s3://$RELEASE_STATE_BUCKET/$duckdb_version/clients/$client/state.json`

Duplicate state writes fail by using S3 create-only semantics. The GitHub
workflow also queues duplicate event/version/client runs with a concurrency
group and `cancel-in-progress: false`.

Downstream workflows receive:

- `duckdb_version`
- `duckdb_commit`
- `payload`, for example `{"phase":"core_ready"}` or
  `{"phase":"client_ready","name":"python"}`

Endpoints are configured in `endpoints.yml` and grouped by hook:

```yaml
hooks:
  core_ready:
    python:
      workflow: duckdb/duckdb-python/OnCoreReady.yml@main
```

## Local MinIO Run

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
