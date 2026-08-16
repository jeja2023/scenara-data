"""已发布契约的只读镜像。

`scenara-contracts` 是能力、实体、接口、事件、错误码和状态的唯一来源。本模块只登记
本仓库消费/生产的契约标识，供代码、配置和门禁三方交叉校验（规范 68、74）。任何新增
跨仓库结构必须先在 `scenara-contracts` 发布，再更新此处并同步 `configs/contracts/`。
"""

from __future__ import annotations

from types import MappingProxyType

CONTRACT_PACKAGE = "@scenara/repository-contracts"
CONTRACT_VERSION = "1.0.0"
CONTRACT_SOURCE_REPOSITORY = "scenara-contracts"
CONTRACT_MANIFEST_SHA256 = "4b070ce7e8d11f6c21641559c844b736482fa38e726b0778eb2d9c2834feecd6"

EVENT_ENVELOPE_VERSION = "1.0"
ERROR_ENVELOPE_VERSION = "1.0"
EVENT_PRODUCER = "scenara-data"

#: 本仓库消费的契约。
CONSUMED_CONTRACTS: tuple[str, ...] = (
    "hard-sample-handoff",
    "object-reference",
    "event-envelope",
    "iam-context",
)

#: 本仓库生产的契约。
PRODUCED_CONTRACTS: tuple[str, ...] = (
    "dataset-version-input",
    "object-reference",
    "api-error",
    "event-envelope",
)

#: 平台能力 ID（规范 9）：小写下划线、稳定、唯一。
CAPABILITIES: tuple[str, ...] = (
    "data_asset",
    "sample",
    "dataset",
    "dataset_version",
    "dataset_manifest",
    "annotation",
    "data_quality",
    "data_lineage",
    "hard_sample_intake",
    "dataset_builder",
    "dataset_import",
    "dataset_export",
    "dataset_access_grant",
)

#: 权限 ID（指南 10）：必须与 `configs/permissions/data-permissions.yml` 一致。
PERMISSIONS: tuple[str, ...] = (
    "data.dataset.create",
    "data.dataset.read",
    "data.dataset.update",
    "data.dataset.publish",
    "data.dataset.archive",
    "data.sample.create",
    "data.sample.read",
    "data.annotation.create",
    "data.annotation.review",
    "data.quality.run",
    "data.lineage.read",
    "data.import.execute",
    "data.export.execute",
    "data.hard_sample.import",
)

#: 已登记错误码（规范 35）：含义不随语言或项目变化。
ERROR_CODES: tuple[str, ...] = (
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "RESOURCE_NOT_FOUND",
    "RESOURCE_CONFLICT",
    "IMMUTABLE_RESOURCE",
    "IDEMPOTENCY_CONFLICT",
    "INVALID_STATE_TRANSITION",
    "VALIDATION_FAILED",
    "DEPENDENCY_UNAVAILABLE",
    "INTERNAL_ERROR",
)

#: 本仓库发布的事件（指南 12）。
PUBLISHED_EVENTS: tuple[str, ...] = (
    "dataset.created",
    "dataset.updated",
    "dataset.archived",
    "dataset.version.created",
    "dataset.version.ready",
    "dataset.version.published",
    "dataset.version.archived",
    "dataset.version.failed",
    "annotation.task.created",
    "annotation.submitted",
    "annotation.reviewed",
    "quality.completed",
    "quality.failed",
    "hard_sample.imported",
    "hard_sample.import.failed",
    "dataset.migration.completed",
    "dataset.access_grant.created",
)

#: 本仓库消费的事件（指南 12）。
CONSUMED_EVENTS: tuple[str, ...] = ("hard_sample.created",)

#: Dataset Version 对 Model 输出的契约版本。
DATASET_VERSION_INPUT_SCHEMA_VERSION = "1.0"
#: Core 投递难例清单的契约版本。
HARD_SAMPLE_MANIFEST_SCHEMA_VERSION = "1.0"
#: 迁移包清单契约版本。
MIGRATION_PACKAGE_SCHEMA_VERSION = "1.0"

#: 状态线值（规范 38）：代码枚举名可大写，跨仓库输出统一小写。
REGISTERED_STATES: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        "dataset": ("draft", "active", "archived"),
        "dataset_version": ("draft", "building", "ready", "published", "archived", "failed"),
        "annotation": ("draft", "in_review", "accepted", "rejected"),
        "annotation_task": (
            "pending",
            "assigned",
            "in_progress",
            "submitted",
            "approved",
            "rejected",
            "cancelled",
        ),
        "job": ("queued", "running", "succeeded", "failed", "cancelled"),
        "quality": ("passed", "warning", "failed"),
    }
)


def assert_registered_event(event_type: str) -> str:
    """禁止绕过契约新增事件类型（规范 34、61）。"""
    if event_type not in PUBLISHED_EVENTS:
        raise ValueError(f"unregistered event type: {event_type}")
    return event_type


def assert_registered_permission(permission: str) -> str:
    if permission not in PERMISSIONS:
        raise ValueError(f"unregistered permission id: {permission}")
    return permission
