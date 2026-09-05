# 运维、容量与容灾恢复

- **责任团队**：景枢数据团队。负责数据库、对象存储、数据备份、灾难恢复、安全告警和版本发布值班。
- **协同边界**：共享身份与访问管理（IAM）、API 网关和统一告警入口由核心平台（Core）团队负责。

初始容量基线按 100 万样本元数据、10 万标注/日、1 万数据集版本、对象内容外置 S3 架构设计。正式上线前必须使用目标生产数据重新验证吞吐量、响应延迟、存储增长率和导出背压，不得将本基线直接视为资格报告。

- **PostgreSQL 数据库**：每日执行全量备份，配合持续预写日志（WAL）或等价增量备份保护；容灾目标为数据恢复点目标（RPO）<= 15 分钟，恢复时间目标（RTO）<= 4 小时。
- **对象存储**：开启版本控制、生命周期管理和不可变发布对象写保护；每日执行对象清单与 SHA-256 摘要巡检。
- **Redis 缓存**：仅用于缓存加速、分布式锁、作业队列和临时状态，不作为业务事实来源；允许从 PostgreSQL/Outbox 完整重建。
- **发件箱工作进程（Outbox）**：脚本 `scripts/run_outbox.py` 作为独立守护进程或 `data-outbox` 容器服务运行，负责将已提交业务事实对应的事件投递到核心平台；投递失败进入指数退避与死信队列，不回滚已持久化的业务事实。
- **事件回传服务凭据**：环境变量 `SCENARA_DATA_CORE_EVENT_TOKEN` 必须与核心平台内部事件接收端点的服务令牌保持一致，严禁与外部用户业务令牌混用。
- **容灾恢复演练**：至少每季度开展一次全量数据库、清单和样本对象的灾难恢复演练，验证记录数、SHA-256 哈希值、权限范围和审计链完整性。
- **运维告警规则**：覆盖 API 错误率突增、任务队列积压、数据集发布失败、清单摘要不一致、自动备份失败、存储容量阈值超限以及越权访问拒绝等核心场景。

## 本地可执行演练工具

以下工具已经纳入仓库，用于在隔离的本地/预生产环境生成可归档证据。所有实际写入或恢复操作都要求显式参数或确认值，默认只读/只报告。

```powershell
# 生成 custom-format PostgreSQL 备份、SHA-256 清单并上传备份桶。
python scripts/backup_postgres.py --output-dir runtime-state/backups

# 复制所有业务对象的版本快照到备份桶，并保存对象恢复清单。
python scripts/backup_object_store.py --output-dir runtime-state/backups

# 仅校验备份；恢复必须再加 --apply 且 --confirmation 等于清单中的 SHA-256。
python scripts/restore_postgres.py --artifact <backup.dump> --manifest <backup.manifest.json> --target-database-url <isolated-db-url>
python scripts/restore_object_store.py --manifest <object-snapshot.json>

# 巡检六个业务桶的版本控制和对象校验和；高风险全量内容复算需加 --verify-content。
python scripts/verify_object_inventory.py

# 默认只列出死信；重建单条事件需显式 --apply。
python scripts/rebuild_outbox.py --event-id <evt_id>
python scripts/rebuild_outbox.py --event-id <evt_id> --apply --operator <operator-id>

# 只读 API 压测，生成延迟和错误率报告。
python scripts/load_test_api.py --base-url https://data-preprod.example --tenant-id <tenant> --project-id <project> --report runtime-state/reports/load.json

# 生产 profile 下检查 TLS 依赖、对象版本、迁移摘要和 Outbox 死信，生成发布证据。
python scripts/preproduction_check.py --report runtime-state/reports/preproduction.json
```

Core/Model 本地联调可使用 `scripts/sign_context.py` 生成与服务端完全一致的 HMAC 身份上下文头。该工具只输出占位 Bearer 令牌，绝不输出签名密钥。
