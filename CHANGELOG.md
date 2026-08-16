# 更新日志

## [0.1.3] - 2026-08-16

- 增加独立 Vue 3 + Vite 数据工作台，提供总览、数据集、版本治理、难例导入和运维探针页面。
- 增加独立前端的统一主题、导航壳、连接设置和本机后端联调入口，支持自动端口回退与本机服务探测。
- 增加后端 CORS、前端构建与类型检查、以及面向本机 PostgreSQL/Redis/MinIO 的集成验证入口。
- 补齐前端与部署、测试文档，统一版本号到 0.1.3。

## [0.1.2] - 2026-08-16

- 增加正式 `scenara-contracts` 发布物校验、schema/example 验证和仓库门禁接入。
- 增加跨仓库 E2E、真实 PostgreSQL/Redis/MinIO 集成 smoke、隔离 schema 迁移执行和本机环境参数化。
- 增加独立 Outbox Worker、Core 事件接收端、事件幂等与审计回传。
- 增加迁移导出/导入闭环、包内 Manifest 物化、样本与版本成员恢复。

## [0.1.1] - 2026-08-16

- 实现内部 Dataset、Sample、Annotation、Quality、Lineage 和 Hard Sample API，以及 PostgreSQL、S3、Redis 适配器。
- 增加事务内幂等记录、Outbox 领取租约、质量失败报告持久化和 tenant/project 作用域写入校验。
- 增加迁移包失败报告与终态幂等处理、API 工作流和基础设施自动化测试。
- 将开发 Compose 调整为 PostgreSQL 事实存储模式，并在启动前执行迁移和对象桶初始化。
- 增加正式 `scenara-contracts` 发布物校验、跨仓库 E2E、独立 Outbox Worker，以及真实 PostgreSQL/Redis/MinIO 集成 smoke。

## [0.1.0] - 2026-08-15

- 建立 `scenara-data` 独立仓库骨架。
- 增加 Dataset、Dataset Version、Sample、Annotation、Manifest 和 Object Reference 领域模型。
- 增加不可变 Dataset Version 状态转换、领域端口、健康检查和自动测试。
- 锁定 `@scenara/repository-contracts` `1.0.0`，记录难例输入和数据集版本输出依赖。
- 建立 IAM 透传、审计回传、数据库/对象存储、迁移回滚、容量备份恢复和安全责任文档。
