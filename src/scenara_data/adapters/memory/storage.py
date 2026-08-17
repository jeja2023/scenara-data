"""内存对象存储：不可变写入、读取校验和可验证的短期授权地址。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from threading import RLock
from urllib.parse import parse_qs, quote, unquote, urlparse

from scenara_data.domain.models import ObjectReference

PRESIGN_HOST = "https://object-storage.invalid"


class PresignedUrlError(RuntimeError):
    """授权地址无效、被篡改或已过期。"""


class InMemoryObjectStorage:
    """开发用兼容 S3 的对象存储替身；保持提供方中立的同一端口语义。"""

    def __init__(self, bucket: str = "scenara-datasets", *, signing_key: bytes | None = None) -> None:
        self._default_bucket = bucket
        self._objects: dict[tuple[str, str, str | None], bytes] = {}
        self._references: dict[tuple[str, str], ObjectReference] = {}
        self._signing_key = signing_key or secrets.token_bytes(32)
        self._lock = RLock()

    @property
    def default_bucket(self) -> str:
        return self._default_bucket

    def ping(self) -> bool:
        return True

    def put_immutable(
        self, key: str, content: bytes, content_type: str, *, bucket: str | None = None
    ) -> ObjectReference:
        target = bucket or self._default_bucket
        with self._lock:
            identity = (target, key)
            existing = self._references.get(identity)
            if existing is not None:
                stored = self._objects[(existing.bucket, existing.key, existing.version)]
                if stored == content and existing.content_type == content_type:
                    return existing
                raise ValueError("不可变对象已存在且内容不同")
            reference = ObjectReference(
                bucket=target,
                key=key,
                version=f"version:{secrets.token_hex(16)}",
                checksum=f"sha256:{hashlib.sha256(content).hexdigest()}",
                size_bytes=len(content),
                content_type=content_type,
            )
            self._objects[(reference.bucket, reference.key, reference.version)] = content
            self._references[identity] = reference
            return reference

    def register_external(self, reference: ObjectReference, content: bytes) -> None:
        """登记 Core 通过对象引用授权的来源内容（开发环境替代预签名读取）。"""
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if digest != reference.checksum or len(content) != reference.size_bytes:
            raise ValueError("外部对象与其引用不一致")
        with self._lock:
            self._objects[(reference.bucket, reference.key, reference.version)] = content
            self._references[(reference.bucket, reference.key)] = reference

    def read_verified(self, reference: ObjectReference) -> bytes:
        content = self._objects.get((reference.bucket, reference.key, reference.version))
        if content is None:
            raise FileNotFoundError(f"{reference.bucket}/{reference.key}")
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if digest != reference.checksum or len(content) != reference.size_bytes:
            raise ValueError("对象校验和或大小不匹配")
        return content

    def presign_read(self, reference: ObjectReference, expires_in_seconds: int) -> str:
        if expires_in_seconds <= 0:
            raise ValueError("预签名 URL 的有效期必须为正数")
        if (reference.bucket, reference.key) not in self._references:
            raise FileNotFoundError(f"{reference.bucket}/{reference.key}")
        expires_at = int(datetime.now(UTC).timestamp()) + expires_in_seconds
        path = f"/{quote(reference.bucket)}/{quote(reference.key)}"
        signature = self._sign(reference, expires_at)
        version = reference.version or ""
        return f"{PRESIGN_HOST}{path}?version={quote(version)}&expires={expires_at}&signature={signature}"

    def resolve_presigned(self, url: str, *, now: datetime | None = None) -> bytes:
        """校验并读取授权地址；用于验证过期与篡改的失败路径。"""
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            raise PresignedUrlError("授权地址路径无效")
        bucket, key = (unquote(part) for part in parts)
        try:
            expires_at = int(query.get("expires", ["0"])[0])
            signature = query.get("signature", [""])[0]
            version = query.get("version", [""])[0] or None
        except ValueError as exc:
            raise PresignedUrlError("授权地址参数无效") from exc
        reference = self._references.get((bucket, key))
        if reference is None or reference.version != version:
            raise PresignedUrlError("授权地址指向的对象不存在")
        moment = now or datetime.now(UTC)
        if expires_at <= int(moment.timestamp()):
            raise PresignedUrlError("授权地址已过期")
        if not hmac.compare_digest(signature, self._sign(reference, expires_at)):
            raise PresignedUrlError("授权地址签名无效")
        return self.read_verified(reference)

    def _sign(self, reference: ObjectReference, expires_at: int) -> str:
        payload = "\n".join(
            [reference.bucket, reference.key, reference.version or "", reference.checksum, str(expires_at)]
        )
        return hmac.new(self._signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
