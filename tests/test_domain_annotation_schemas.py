from __future__ import annotations

import pytest

from scenara_data.domain.annotation_schemas import (
    AnnotationSchemaError,
    published_annotation_schemas,
    validate_annotation_payload,
)


def test_published_multidomain_annotation_catalog_is_digest_locked() -> None:
    assert set(published_annotation_schemas()) == {
        "scenara.feedback.correction.v1",
        "scenara.portrait.detection.v1",
        "scenara.portrait.surveillance-review.v1",
        "scenara.ocr.document.v1",
        "scenara.behavior.action.v1",
        "scenara.fashion.style.v1",
    }


@pytest.mark.parametrize(
    ("schema_id", "media_kind", "payload"),
    (
        (
            "scenara.portrait.surveillance-review.v1",
            "image",
            {
                "alert_id": "alt_localqualification",
                "triage_reason": "人工排除误报",
                "review_outcome": "false_positive",
            },
        ),
        (
            "scenara.ocr.document.v1",
            "document",
            {
                "text": "景枢",
                "blocks": [
                    {
                        "text": "景枢",
                        "block_type": "title",
                        "reading_order": 0,
                        "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    }
                ],
            },
        ),
        (
            "scenara.behavior.action.v1",
            "video",
            {"actions": [{"action_type": "fall", "start_ms": 100, "end_ms": 500}]},
        ),
        (
            "scenara.fashion.style.v1",
            "image",
            {
                "cosplay": [],
                "clothing_styles": [{"style_type": "hanfu", "style_label": "汉服"}],
                "accessories": [],
            },
        ),
    ),
)
def test_multidomain_annotation_payloads_are_validated(
    schema_id: str,
    media_kind: str,
    payload: dict[str, object],
) -> None:
    definition = validate_annotation_payload(schema_id, payload, media_kind=media_kind)
    assert definition["schema_id"] == schema_id


def test_behavior_temporal_range_fails_closed() -> None:
    with pytest.raises(AnnotationSchemaError, match="不能早于"):
        validate_annotation_payload(
            "scenara.behavior.action.v1",
            {"actions": [{"action_type": "fall", "start_ms": 500, "end_ms": 100}]},
            media_kind="video",
        )


def test_unknown_schema_and_media_mismatch_fail_closed() -> None:
    with pytest.raises(AnnotationSchemaError, match="未发布"):
        validate_annotation_payload("private.schema", {}, media_kind="image")
    with pytest.raises(AnnotationSchemaError, match="不支持媒体类型"):
        validate_annotation_payload(
            "scenara.behavior.action.v1",
            {"actions": []},
            media_kind="image",
        )
