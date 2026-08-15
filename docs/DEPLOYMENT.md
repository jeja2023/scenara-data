# 部署文档

初始容器入口为 `deploy/Dockerfile`，Compose 提供独立 PostgreSQL、Redis 和 MinIO 开发基线。正式环境必须使用受管密钥、非 root 容器、网络隔离、TLS、最小权限服务账号和独立备份策略。

Data 不部署独立 Console、用户目录或 API 网关。Core 代理或聚合领域 API 时必须透传 organization/project/principal/permission/request/trace/idempotency 上下文，Data 仍独立执行授权。
