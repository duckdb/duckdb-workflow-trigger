from __future__ import annotations

import json
import os
from dataclasses import dataclass

import boto3
import botocore.exceptions
import duckdb

from release_dispatcher.models import ReleaseState


class StateAlreadyExistsError(RuntimeError):
    pass


@dataclass(frozen=True)
class S3Settings:
    bucket: str
    endpoint_url: str | None = None
    region_name: str | None = None


class S3StateStore:
    def __init__(self, settings: S3Settings, s3_client=None) -> None:
        self.settings = settings
        self.s3_client = s3_client or boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region_name,
        )

    def create_state(self, state: ReleaseState) -> str:
        key = state.state_key
        body = json.dumps(state.to_json_dict(), indent=2, sort_keys=True).encode("utf-8")
        try:
            self.s3_client.put_object(
                Bucket=self.settings.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except botocore.exceptions.ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise StateAlreadyExistsError(
                    f"s3://{self.settings.bucket}/{key} already exists"
                ) from exc
            raise
        return key


def query_release_states(
    *,
    bucket: str,
    version: str,
    endpoint_url: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region: str | None = None,
) -> duckdb.DuckDBPyRelation:
    con = duckdb.connect(":memory:")
    con.install_extension("httpfs")
    con.load_extension("httpfs")
    configure_duckdb_s3(
        con,
        endpoint_url=endpoint_url or os.getenv("AWS_ENDPOINT_URL_S3"),
        access_key_id=access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
        secret_access_key=secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        region=region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )
    return con.sql(f"SELECT * FROM read_json_auto('s3://{bucket}/{version}/**/state.json')")


def configure_duckdb_s3(
    con: duckdb.DuckDBPyConnection,
    *,
    endpoint_url: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
    region: str | None,
) -> None:
    if endpoint_url:
        endpoint = endpoint_url.removeprefix("http://").removeprefix("https://")
        _set_duckdb_string(con, "s3_endpoint", endpoint)
        con.execute("SET s3_url_style = 'path'")
        con.execute(f"SET s3_use_ssl = {str(endpoint_url.startswith('https://')).lower()}")
    if access_key_id:
        _set_duckdb_string(con, "s3_access_key_id", access_key_id)
    if secret_access_key:
        _set_duckdb_string(con, "s3_secret_access_key", secret_access_key)
    if region:
        _set_duckdb_string(con, "s3_region", region)


def _set_duckdb_string(con: duckdb.DuckDBPyConnection, name: str, value: str) -> None:
    escaped = value.replace("'", "''")
    con.execute(f"SET {name} = '{escaped}'")
