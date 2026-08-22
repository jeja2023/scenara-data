# scenara-data 剩余任务计划

**适用规范：** `景枢平台总体开发规范.md` 1.3.0

**当前版本：** `0.1.5`

**当前成熟度：** `implemented`（未达到 `qualified` 或 `production_ready`）

## 已完成基线

以下能力已经由本仓库代码和回归测试覆盖：

- Dataset、Dataset Version、Sample、Annotation、Quality、Lineage、Hard Sample、Builder 和 Provider。
- `/internal/v1/` 领域 API、租户/项目作用域、幂等、审计、错误信封、请求追踪和 Outbox。
- PostgreSQL 迁移、内存适配器、对象存储适配器、Redis 任务适配器和迁移包导入。
- `hard-sample-handoff`、`dataset-version-input` 的已发布契约校验，以及 Core ASGI 端到端回归。

## 剩余交付

| 编号 | 状态 | 任务 | 责任边界 | 验收证据 |
| --- | --- | --- | --- | --- |
| DATA-P1 | implemented | 完成 Core 导出包的真实 PostgreSQL/S3 导入、数量/ID/摘要影子比对 | Data + Core | 带 manifest/checksums 的迁移报告、重复导入报告 |
| DATA-P2 | implemented | 完成 Sample/Annotation/Quality/Lineage 在真实基础设施上的并发、冻结、失败重试和恢复演练 | Data | 集成测试、恢复报告、权限与审计查询 |
| DATA-P3 | planned | 运行 Data 独立服务的备份、恢复、容量和 Redis pending 消息演练 | Data/Deploy | RPO/RTO、容量曲线、pending 重建报告 |
| DATA-P4 | planned | Core 影子读、只读旧表、正式远程切流和回滚窗口 | Core + Data | 流量证明、切流/回滚日志、旧写路径退役记录 |
| DATA-P5 | planned | 将 Model 服务的真实服务间授权接入，补充跨仓库 DatasetVersionReference 消费报告 | Data + Model | 授权拒绝/通过、摘要校验、无数据库直连证明 |
| DATA-P6 | planned | 扩展公共 API/事件目录时同步 `scenara-contracts` 新版本 | Data + Contracts | 发布包版本、兼容矩阵和迁移说明 |

## 执行顺序

```text
DATA-P1 -> DATA-P2 -> DATA-P3 -> DATA-P4
                 \-> DATA-P5 -> DATA-P6（按契约变更触发）
```

未取得真实基础设施、备份恢复和切流证据前，本仓库保持 `implemented`，不得声明 `qualified` 或 `production_ready`。开发验证使用：

```powershell
.\.venv\Scripts\python.exe -m pytest -rA
.\.venv\Scripts\python.exe scripts\repository_gate.py
.\.venv\Scripts\python.exe scripts\validate_repository_contracts.py
```
