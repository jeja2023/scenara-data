# 部署文档

初始容器入口为 `deploy/Dockerfile`，Compose 提供独立 PostgreSQL、Redis 和 MinIO 开发基线：`data-migrate` 在 API 启动前执行版本化迁移，`minio-init` 创建所有业务桶，`data-outbox` 负责异步投递到 Core 事件端点，API 以 `postgres` 事实存储模式启动，并由 `/readyz` 检查数据库、对象存储和 Redis 锁。

```powershell
docker compose -f deploy/compose.yml up --build
```

默认还会把 PostgreSQL `5432`、Redis `6379`、MinIO `9000/9001` 和 API `8081` 暴露到宿主机，供 `pytest -m integration` 和本地排障直接连通。

`postgres` 运行模式还要求配置 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 与 `SCENARA_DATA_CORE_EVENT_TOKEN`；缺失时 API 和独立 Outbox 工作进程都会在启动阶段拒绝运行，避免事件回传链路被静默跳过。

本机一键启动可直接执行 [start.py](/D:/project/scenara-data/start.py)。默认 `all` 模式会先探测 PostgreSQL、Redis 和 MinIO 是否可达，再启动数据 API 与前端工作台；也可以通过 `--mode backend` 或 `--mode frontend` 单独启动。

数据平台前端采用独立 Vue 3 + Vite 工作台，当前版本为 `0.1.4`，目录为 `frontend/data-console`。工作台已完成全面中文化，并提供总览、数据集、版本治理、难例导入和运维探针页面。开发时可通过 `VITE_DATA_API_BASE` 指定后端地址，例如 `http://127.0.0.1:8082`。

工作台启动后会分别请求 `/readyz`、`/health` 和业务列表接口。业务列表发生分页校验失败时，页面会保留真实探针状态并展示业务错误；列表请求应使用后端契约允许的 `limit=100`。移动端部署验收应覆盖顶部导航、连接设置、导航抽屉、长文本换行和表格横向滚动。

正式环境必须使用受管密钥、非 root 容器、网络隔离、TLS、最小权限服务账号和独立备份策略。

数据平台不部署独立控制台、用户目录或 API 网关。Core 平台代理或聚合领域 API 时必须透传组织、项目、主体、权限、请求、追踪和幂等上下文，数据平台仍独立执行授权。
