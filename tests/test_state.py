import os
import time
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config

from release_dispatcher.models import parse_release_state
from release_dispatcher.state import (
    S3Settings,
    S3StateStore,
    StateAlreadyExistsError,
    query_release_states,
)


@pytest.fixture()
def s3_env():
    required = {
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "AWS_REGION": os.getenv("AWS_REGION"),
        "AWS_ENDPOINT_URL_S3": os.getenv("AWS_ENDPOINT_URL_S3"),
        "RELEASE_STATE_BUCKET": os.getenv("RELEASE_STATE_BUCKET"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        pytest.fail(f"missing MinIO test environment variable(s): {', '.join(missing)}")
    return required


@pytest.fixture()
def s3_client(s3_env):
    client = boto3.client(
        "s3",
        endpoint_url=s3_env["AWS_ENDPOINT_URL_S3"],
        region_name=s3_env["AWS_REGION"],
        aws_access_key_id=s3_env["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=s3_env["AWS_SECRET_ACCESS_KEY"],
        config=Config(s3={"addressing_style": "path"}),
    )
    _wait_for_bucket(client, s3_env["RELEASE_STATE_BUCKET"])
    return client


@pytest.fixture()
def state_store(s3_env):
    return S3StateStore(
        S3Settings(
            bucket=s3_env["RELEASE_STATE_BUCKET"],
            endpoint_url=s3_env["AWS_ENDPOINT_URL_S3"],
            region_name=s3_env["AWS_REGION"],
        )
    )


@pytest.fixture()
def version_prefix(s3_client, s3_env):
    version = f"pytest-{uuid4().hex}"
    yield version
    _delete_prefix(s3_client, s3_env["RELEASE_STATE_BUCKET"], f"{version}/")


def test_create_core_ready_state_in_minio(state_store, s3_client, s3_env, version_prefix):
    state = parse_release_state(
        event="core_ready",
        duckdb_version=version_prefix,
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    key = state_store.create_state(state)
    stored = s3_client.get_object(Bucket=s3_env["RELEASE_STATE_BUCKET"], Key=key)

    assert key == f"{version_prefix}/core/state.json"
    assert stored["ContentType"] == "application/json"
    assert b'"event": "core_ready"' in stored["Body"].read()


def test_duplicate_state_write_fails_in_minio(state_store, version_prefix):
    state = parse_release_state(
        event="core_ready",
        duckdb_version=version_prefix,
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
    )

    state_store.create_state(state)

    with pytest.raises(StateAlreadyExistsError, match="already exists"):
        state_store.create_state(state)


def test_create_client_ready_state_in_minio(state_store, s3_client, s3_env, version_prefix):
    state = parse_release_state(
        event="client_ready",
        duckdb_version=version_prefix,
        duckdb_commit="0123456789abcdef0123456789abcdef01234567",
        status="success",
        client="python",
    )

    key = state_store.create_state(state)
    stored = s3_client.get_object(Bucket=s3_env["RELEASE_STATE_BUCKET"], Key=key)

    assert key == f"{version_prefix}/clients/python/state.json"
    assert b'"client": "python"' in stored["Body"].read()


def test_query_release_states_with_duckdb(state_store, s3_env, version_prefix):
    state_store.create_state(
        parse_release_state(
            event="core_ready",
            duckdb_version=version_prefix,
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
        )
    )
    state_store.create_state(
        parse_release_state(
            event="client_ready",
            duckdb_version=version_prefix,
            duckdb_commit="0123456789abcdef0123456789abcdef01234567",
            status="success",
            client="python",
        )
    )

    relation = query_release_states(
        bucket=s3_env["RELEASE_STATE_BUCKET"],
        version=version_prefix,
        endpoint_url=s3_env["AWS_ENDPOINT_URL_S3"],
    )
    records = [dict(zip(relation.columns, row, strict=True)) for row in relation.fetchall()]

    assert {record.get("client") for record in records} == {"python", None}
    assert {record["event"] for record in records} == {"core_ready", "client_ready"}


def _wait_for_bucket(client, bucket: str) -> None:
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            client.head_bucket(Bucket=bucket)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(f"bucket {bucket} was not available") from last_error


def _delete_prefix(client, bucket: str, prefix: str) -> None:
    listed = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [{"Key": item["Key"]} for item in listed.get("Contents", [])]
    if objects:
        client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
