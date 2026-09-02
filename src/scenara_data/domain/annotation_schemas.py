from __future__ import annotations

import hashlib
import json
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CATALOG_RELEASE = "1.1.0"
CATALOG_MANIFEST_SHA256 = "0f2a7ffb271320d5be45a92bf9fc63b08656c33c1983ee01413d7131ed4ba278"
CATALOG_ROOT = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "contracts"
    / "domain-annotations"
    / f"v{CATALOG_RELEASE}"
)


class AnnotationSchemaError(ValueError):
    pass


def normalized_media_kind(value: str) -> str:
    lowered = value.strip().lower()
    if "/" not in lowered:
        return lowered
    if lowered.startswith("image/"):
        return "image"
    if lowered.startswith("video/"):
        return "video"
    if lowered in {"application/pdf", "application/msword"} or lowered.startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    ):
        return "document"
    guessed = mimetypes.guess_extension(lowered)
    return guessed.lstrip(".") if guessed else lowered


@lru_cache(maxsize=1)
def published_annotation_schemas() -> dict[str, dict[str, Any]]:
    manifest_path = CATALOG_ROOT / "manifest.json"
    content = manifest_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != CATALOG_MANIFEST_SHA256:
        raise AnnotationSchemaError("领域标注模式清单摘要不匹配")
    manifest = json.loads(content)
    if manifest.get("release_version") != CATALOG_RELEASE:
        raise AnnotationSchemaError("领域标注模式发布版本不匹配")
    schemas: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("schemas", []):
        schema_id = str(entry["schema_id"])
        path = CATALOG_ROOT / Path(str(entry["path"])).name
        document = path.read_bytes()
        if hashlib.sha256(document).hexdigest() != entry["sha256"]:
            raise AnnotationSchemaError(f"领域标注模式摘要不匹配：{schema_id}")
        definition = json.loads(document)
        if definition.get("schema_id") != schema_id:
            raise AnnotationSchemaError(f"领域标注模式标识不匹配：{schema_id}")
        payload_schema = definition.get("payload_schema")
        if not isinstance(payload_schema, dict):
            raise AnnotationSchemaError(f"领域标注模式缺少 payload_schema：{schema_id}")
        Draft202012Validator.check_schema(payload_schema)
        schemas[schema_id] = definition
    return schemas


def annotation_schema_definition(schema_id: str) -> dict[str, Any]:
    definition = published_annotation_schemas().get(schema_id)
    if definition is None:
        raise AnnotationSchemaError(f"未发布的领域标注模式：{schema_id}")
    return definition


def validate_annotation_payload(
    schema_id: str,
    payload: dict[str, Any],
    *,
    media_kind: str | None = None,
) -> dict[str, Any]:
    definition = annotation_schema_definition(schema_id)
    supported = set(definition["supported_media_kinds"])
    normalized_kind = normalized_media_kind(media_kind) if media_kind is not None else None
    if normalized_kind is not None and normalized_kind not in supported:
        raise AnnotationSchemaError(f"标注模式 {schema_id} 不支持媒体类型 {media_kind}")
    errors = sorted(
        Draft202012Validator(definition["payload_schema"]).iter_errors(payload),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "$"
        raise AnnotationSchemaError(f"标注内容不符合 {schema_id}：{location}: {error.message}")
    if definition["domain"] == "behavior":
        for collection in ("actions", "segments"):
            for index, item in enumerate(payload.get(collection, [])):
                if item["end_ms"] < item["start_ms"]:
                    raise AnnotationSchemaError(
                        f"标注内容不符合 {schema_id}：{collection}.{index}.end_ms 不能早于 start_ms"
                    )
    elif definition["domain"] == "fashion":
        if not any(payload.get(name) for name in ("cosplay", "clothing_styles", "accessories")):
            raise AnnotationSchemaError(f"标注内容不符合 {schema_id}：至少包含一项服饰标签")
    elif definition["domain"] == "ocr":
        orders = [item.get("reading_order") for item in payload.get("blocks", []) if "reading_order" in item]
        if len(orders) != len(set(orders)):
            raise AnnotationSchemaError(f"标注内容不符合 {schema_id}：reading_order 必须唯一")
    return definition


__all__ = [
    "AnnotationSchemaError",
    "annotation_schema_definition",
    "published_annotation_schemas",
    "validate_annotation_payload",
]
