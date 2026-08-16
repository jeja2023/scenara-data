"""S3-compatible 对象存储 Provider（规范 31、32；MinIO 为第一阶段基线）。

已发布对象不可覆盖，读取时重新校验 SHA-256，跨仓库访问只使用短期预签名地址。
业务层不得判断 Provider、桶名或访问地址。
"""

from __future__ import annotations

import hashlib
from typing import Any

from scenara_data.config import Settings
from scenara_data.domain.models import ObjectReference

NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchVersion", "NoSuchBucket", "404", "NotFound"})
PRECONDITION_CODES = frozenset({"PreconditionFailed", "412"})


class S3ObjectStorage:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self._default_bucket = settings.dataset_bucket
        self._known_buckets = {
            settings.dataset_bucket,
            settings.manifest_bucket,
            settings.import_bucket,
            settings.export_bucket,
            settings.artifact_bucket,
        }
        if client is not None:
            self._client = client
            return
        try:
            import boto3  # 延迟导入：S3 Provider 是可选运行依赖
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("S3 对象存储需要安装 scenara-data[s3]") from exc
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint,
            region_name=settings.object_storage_region,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
        )

    @property
    def default_bucket(self) -> str:
        return self._default_bucket

    def ping(self) -> bool:
        for bucket in sorted(self._known_buckets):
            try:
                self._client.head_bucket(Bucket=bucket)
            except Exception:
                return False
        return True

    def put_immutable(
        self, key: str, content: bytes, content_type: str, *, bucket: str | None = None
    ) -> ObjectReference:
        target = bucket or self._default_bucket
        checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"
        existing = self._head_reference(target, key)
        if existing is not None:
            if existing.checksum == checksum and existing.size_bytes == len(content):
                self.read_verified(existing)
                return existing
            raise ValueError("immutable object already exists with different content")
        try:
            response = self._client.put_object(
                Bucket=target,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": checksum.removeprefix("sha256:")},
                IfNoneMatch="*",
            )
        except Exception as exc:
            if _error_code(exc) in PRECONDITION_CODES:
                existing = self._head_reference(target, key)
                if existing is not None and existing.checksum == checksum:
                    return existing
                raise ValueError("immutable object already exists with different content") from exc
            raise
        return ObjectReference(
            bucket=target,
            key=key,
            version=_version_of(response),
            checksum=checksum,
            size_bytes=len(content),
            content_type=content_type,
        )

    def read_verified(self, reference: ObjectReference) -> bytes:
        parameters = self._object_parameters(reference)
        try:
            response = self._client.get_object(**parameters)
        except Exception as exc:
            if _error_code(exc) in NOT_FOUND_CODES:
                raise FileNotFoundError(f"{reference.bucket}/{reference.key}") from exc
            raise
        content = response["Body"].read()
        checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if checksum != reference.checksum or len(content) != reference.size_bytes:
            raise ValueError("object checksum or size mismatch")
        return content

    def presign_read(self, reference: ObjectReference, expires_in_seconds: int) -> str:
        if expires_in_seconds <= 0:
            raise ValueError("presigned URL expiry must be positive")
        if self._head_reference(reference.bucket, reference.key) is None:
            raise FileNotFoundError(f"{reference.bucket}/{reference.key}")
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params=self._object_parameters(reference),
                ExpiresIn=expires_in_seconds,
            )
        )

    @staticmethod
    def _object_parameters(reference: ObjectReference) -> dict[str, Any]:
        parameters: dict[str, Any] = {"Bucket": reference.bucket, "Key": reference.key}
        if reference.version and reference.version.startswith("version:"):
            parameters["VersionId"] = reference.version.removeprefix("version:")
        return parameters

    def _head_reference(self, bucket: str, key: str) -> ObjectReference | None:
        try:
            response = self._client.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if _error_code(exc) in NOT_FOUND_CODES:
                return None
            raise
        metadata_checksum = response.get("Metadata", {}).get("sha256")
        if not metadata_checksum:
            return None
        return ObjectReference(
            bucket=bucket,
            key=key,
            version=_version_of(response),
            checksum=f"sha256:{metadata_checksum}",
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType", "application/octet-stream"),
        )


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str(response.get("Error", {}).get("Code", ""))
    return ""


def _version_of(response: dict[str, Any]) -> str:
    version_id = response.get("VersionId")
    if version_id:
        return f"version:{version_id}"
    etag = str(response.get("ETag", "")).strip('"')
    return f"etag:{etag}" if etag else "etag:unknown"
