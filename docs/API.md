# API 接口文档

当前已实现（implemented）版本为 `0.1.10`，提供内部业务 API、运维探针和独立工作台本地登录入口。公共业务 `/api/v1/` 仍由核心平台（Core）网关代理，数据平台业务接口只暴露内部路径 `/internal/v1/`。

| 请求方法 | 接口路径 | 认证方式 | 用途说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | 无 | 独立数据工作台本地登录，签发短期工作台会话令牌 |
| GET | `/livez`、`/health` | 无 | 存活探针 |
| GET | `/readyz` | 无 | PostgreSQL 与对象存储真实就绪状态检查 |
| GET | `/metrics` | 无 | Prometheus 监控指标采集 |

`/api/v1/auth/login` 仅服务于独立前端直连开发场景，不替代核心平台的统一身份与访问管理（Core IAM）。生产配置默认禁用该入口（`SCENARA_DATA_CONSOLE_LOGIN_ENABLED=false`），改由 Core 网关提供身份事实。登录令牌访问 `/internal/v1/` 时由后端恢复租户、项目、主体、权限范围和产品授权。

生产环境的服务间调用除 Bearer 服务凭据外，还必须携带 Core 使用独立密钥签发的短时身份上下文：`X-Scenara-Context-Timestamp`（Unix 秒）和 `X-Scenara-Context-Signature`。签名内容是以 UTF-8 编码、`sort_keys=true`、无空格 JSON 序列化的对象，字段为 `entitlements`、`method`、`path`、`principal_id`、`principal_type`、`project_id`、`request_id`、`scopes`、`tenant_id`、`timestamp`、`trace_id`；数组去重排序后写入。签名算法为 `HMAC-SHA256` 十六进制小写输出。默认有效期为 300 秒；服务端拒绝过期或篡改的上下文，避免凭据持有者伪造租户、项目、主体和权限范围。

所有 `/internal/v1/` 业务写接口都要求核心平台透传的身份上下文和幂等键（`Idempotency-Key`）。核心路径包括：

```text
POST/GET/PATCH /internal/v1/datasets                            # 数据集管理与更新
POST/GET       /internal/v1/datasets/{dataset_id}/versions      # 数据集版本创建与列表
POST           /internal/v1/dataset-versions/{version_id}/transition # 数据集版本状态流转
GET            /internal/v1/dataset-versions/{version_id}/reference  # 数据集版本跨仓引用输出
GET            /internal/v1/dataset-versions/{version_id}/manifest   # 数据集版本清单物化查询
POST           /internal/v1/annotation-tasks                    # 标注任务创建与分发
POST           /internal/v1/hard-sample-manifests               # 难例清单导入与交接
```

数据平台到核心平台的审计与事件回传不复用上述业务 API。发件箱工作进程（`data-outbox`）通过独立的 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 和 `SCENARA_DATA_CORE_EVENT_TOKEN` 把正式事件信封投递到核心平台的内部接收端点；投递失败进入发件箱（Outbox）重试与死信机制，不回滚已提交的业务事实。

请求失败统一返回错误信封（`api-error`）；分页使用游标字段 `next_cursor`，每页条数 `limit` 的有效范围为 `1` 到 `100`，调用方不得发送超过 `100` 的值。前端工作台的列表请求统一使用 `limit=100`，并将 `422` 校验错误中的字段位置和原因转换为中文提示。

跨仓输入和输出中的时间字段统一使用以 `Z` 结尾的 UTC RFC3339 格式字符串；当前初始开发阶段直接采用该标准，数值 Unix 时间戳会被契约校验拒绝。

运维探针和业务列表是独立的请求链路：`/readyz` 或 `/health` 可访问时，单个列表接口的校验失败不应被解释为后端离线。客户端应分别记录探针状态和业务加载错误，只有两个探针都无法访问时才显示离线状态。
