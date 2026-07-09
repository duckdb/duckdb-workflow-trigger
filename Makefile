.PHONY: up test typecheck

AWS_ACCESS_KEY_ID ?= minioadmin
AWS_SECRET_ACCESS_KEY ?= minioadmin
AWS_REGION ?= us-east-1
AWS_ENDPOINT_URL_S3 ?= http://localhost:9000
RELEASE_STATE_BUCKET ?= duckdb-release-state
DRY_RUN_GITHUB ?= true

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION
export AWS_ENDPOINT_URL_S3
export RELEASE_STATE_BUCKET
export DRY_RUN_GITHUB

up:
	docker compose up -d minio
	docker compose run --rm create-bucket

test:
	uv run pytest

typecheck:
	uv run ruff check .
