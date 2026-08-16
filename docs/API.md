# API 文档

当前 `implemented` 版本提供内部业务 API 和运维探针。公共 `/api/v1/` 仍由 Core 网关代理，Data 只暴露 `/internal/v1/`。

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| GET | `/livez`、`/health` | 无 | 存活探针 |
| GET | `/readyz` | 无 | PostgreSQL/对象存储真实就绪检查 |
| GET | `/metrics` | 无 | Prometheus 指标 |

所有 `/internal/v1/` 业务写接口都要求 Core 透传的身份上下文和 `Idempotency-Key`。核心路径包括：

```text
POST/GET/PATCH /internal/v1/datasets
POST/GET /internal/v1/datasets/{dataset_id}/versions
POST /internal/v1/dataset-versions/{version_id}/transition
GET /internal/v1/dataset-versions/{version_id}/reference
GET /internal/v1/dataset-versions/{version_id}/manifest
POST /internal/v1/annotation-tasks
POST /internal/v1/hard-sample-manifests
```

Data 到 Core 的审计/事件回传不复用上述业务 API。`data-outbox` 通过独立的 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 和 `SCENARA_DATA_CORE_EVENT_TOKEN` 把正式事件信封投递到 Core 的内部接收端点；投递失败进入 Outbox 重试与死信，不回滚已提交业务事实。

请求失败统一返回 `api-error` 信封；分页使用 `next_cursor`，发布后的 Dataset Version、Manifest、样本集合、质量报告引用、血缘快照引用和标注快照不可变。
