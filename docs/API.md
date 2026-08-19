# API 文档

当前 `implemented` 版本为 `0.1.4`，提供内部业务 API、运维探针和独立工作台本地登录入口。公共业务 `/api/v1/` 仍由 Core 网关代理，数据平台业务接口只暴露 `/internal/v1/`。

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | 无 | 独立数据工作台本地登录，会签发短期工作台会话令牌 |
| GET | `/livez`、`/health` | 无 | 存活探针 |
| GET | `/readyz` | 无 | PostgreSQL/对象存储真实就绪检查 |
| GET | `/metrics` | 无 | Prometheus 指标 |

`/api/v1/auth/login` 仅服务独立前端直连场景，不替代 Core IAM。用户名默认来自 `SCENARA_DATA_CONSOLE_USERNAME`，密码默认复用 `SCENARA_DATA_TRUSTED_SERVICE_TOKEN`，也可用 `SCENARA_DATA_CONSOLE_PASSWORD` 单独覆盖。登录令牌访问 `/internal/v1/` 时由后端恢复租户、项目、主体、权限范围和产品授权；服务间调用仍可继续使用原有 Bearer 令牌和透传请求头。

所有 `/internal/v1/` 业务写接口都要求 Core 平台透传的身份上下文和 `Idempotency-Key`。核心路径包括：

```text
POST/GET/PATCH /internal/v1/datasets
POST/GET /internal/v1/datasets/{dataset_id}/versions
POST /internal/v1/dataset-versions/{version_id}/transition
GET /internal/v1/dataset-versions/{version_id}/reference
GET /internal/v1/dataset-versions/{version_id}/manifest
POST /internal/v1/annotation-tasks
POST /internal/v1/hard-sample-manifests
```

数据平台到 Core 平台的审计/事件回传不复用上述业务 API。`data-outbox` 通过独立的 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 和 `SCENARA_DATA_CORE_EVENT_TOKEN` 把正式事件信封投递到 Core 的内部接收端点；投递失败进入 Outbox 重试与死信，不回滚已提交业务事实。

请求失败统一返回 `api-error` 信封；分页使用 `next_cursor`，`limit` 的有效范围为 `1` 到 `100`，调用方不得发送超过 `100` 的值。前端工作台的列表请求统一使用 `limit=100`，并将 `422` 校验错误中的字段位置和原因转换为中文提示。

跨仓输入和输出中的时间字段统一使用以 `Z` 结尾的 UTC RFC3339 字符串；当前初始开发阶段直接采用该标准，数值 Unix 时间戳会被契约校验拒绝。

运维探针和业务列表是独立的请求链路：`/readyz` 或 `/health` 可访问时，单个列表接口的校验失败不应被解释为后端离线。客户端应分别记录探针状态和业务加载错误，只有两个探针都无法访问时才显示离线状态。
