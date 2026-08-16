# 部署文档

初始容器入口为 `deploy/Dockerfile`，Compose 提供独立 PostgreSQL、Redis 和 MinIO 开发基线：`data-migrate` 在 API 启动前执行版本化迁移，`minio-init` 创建所有业务桶，`data-outbox` 负责异步投递到 Core 事件端点，API 以 `postgres` 事实存储模式启动并由 `/readyz` 检查数据库、对象存储和 Redis 锁。

```powershell
docker compose -f deploy/compose.yml up --build
```

默认还会把 PostgreSQL `5432`、Redis `6379`、MinIO `9000/9001` 和 API `8081` 暴露到宿主机，供 `pytest -m integration` 和本地排障直接连通。

`postgres` 运行模式还要求配置 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 与 `SCENARA_DATA_CORE_EVENT_TOKEN`；缺失时 API 和独立 Outbox Worker 都会在启动阶段拒绝运行，避免事件回传链路被静默跳过。

本机一键启动可直接执行 [start.py](/abs/path/D:/project/scenara-data/start.py)。默认 `all` 模式会先探测 PostgreSQL、Redis 和 MinIO 是否可达，再启动 Data API 与前端工作台；也可以通过 `--mode backend` 或 `--mode frontend` 单独启动。

Data 平台前端采用独立 Vue 3 + Vite 工作台，目录为 `frontend/data-console`。开发时可通过 `VITE_DATA_API_BASE` 指定后端地址，例如 `http://127.0.0.1:8082`。

正式环境必须使用受管密钥、非 root 容器、网络隔离、TLS、最小权限服务账号和独立备份策略。

Data 不部署独立 Console、用户目录或 API 网关。Core 代理或聚合领域 API 时必须透传 organization/project/principal/permission/request/trace/idempotency 上下文，Data 仍独立执行授权。
