from __future__ import annotations

import dataclasses
import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings, get_settings


class ObjectNotFound(KeyError):
    """Raised when a requested object key does not exist."""


@dataclasses.dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    last_modified: datetime.datetime | None


class ObjectStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bucket = self.settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, body: str, metadata: dict[str, str] | None = None) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
            Metadata=metadata or {},
        )

    def get(self, key: str) -> str:
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise ObjectNotFound(key) from exc
            raise
        return resp["Body"].read().decode("utf-8")

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def list(self, prefix: str, delimiter: str | None = None) -> tuple[list[str], list[StoredObject]]:
        paginator = self._client.get_paginator("list_objects_v2")
        kwargs: dict = {"Bucket": self.bucket, "Prefix": prefix}
        if delimiter:
            kwargs["Delimiter"] = delimiter

        common_prefixes: list[str] = []
        objects: list[StoredObject] = []
        for page in paginator.paginate(**kwargs):
            for cp in page.get("CommonPrefixes", []):
                common_prefixes.append(cp["Prefix"])
            for obj in page.get("Contents", []):
                objects.append(
                    StoredObject(
                        key=obj["Key"],
                        size=obj.get("Size", 0),
                        last_modified=obj.get("LastModified"),
                    )
                )
        return common_prefixes, objects
