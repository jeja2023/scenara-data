# IAM 透传与审计回传

数据平台不保存用户密码、成员关系、角色、API 密钥或产品授权事实。Core 平台代理请求时透传 `organization_id`、`project_id`、`principal_id`、`permission_scopes`、`request_id`、`trace_id` 和 `idempotency_key`，数据平台使用 Core 信任的短期服务凭据验证来源，并对领域资源独立授权。

数据集创建/发布/删除、标注复核、导出、权限变更和敏感数据删除必须记录 UTC 时间、操作者、组织、项目、请求/追踪 ID、动作、资源、前后状态和结果。审计事件通过版本化事件或服务 API 回传 Core 统一查询入口；回传失败进入 Outbox 重试和死信处理，不阻断已提交业务事实但必须告警。
