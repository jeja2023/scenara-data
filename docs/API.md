# API 文档

当前 `seed` 版本只提供运维探针：

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 返回服务、版本、成熟度和 UTC RFC 3339 时间 |

Dataset、Dataset Version、Annotation、Quality 和 Lineage 业务 API 尚未发布。正式路径统一使用 `/api/v1/`，并在 `scenara-contracts` 定义 Request、Response、Error、Authentication、Authorization、Idempotency、分页和弃用策略后实现。
