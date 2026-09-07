# 测试与质量门禁规范

当前仓库门禁全面覆盖领域状态机、不可变对象引用、UTC RFC 3339 时间探针、身份鉴权与权限隔离、多租户多项目隔离、写操作幂等控制、数据集版本发布不可变性、数据质量检验、发件箱事件投递、数据库迁移、必需架构文档完整性、正式契约版本与哈希摘要锁定、多领域标注模式与示例校验，以及严禁跨仓库源码导入规则。`0.1.8` 额外覆盖 PostgreSQL 归档/分片约束、迁移成员恢复、签名身份上下文、难例失败重试及预生产运维工具；`0.1.9` 额外覆盖数据工作台前端全量中文化、多区域 Tab 切换布局、表格行高与边框规范化、全局分页组件及东八区时间展示校验；`0.1.10` 额外覆盖多受信服务凭据鉴权白名单、共享基础设施测试编排、契约 Schema 正则约束与前端品牌标识统一校验。

```powershell
python -m ruff check src scripts tests
python scripts/validate_repository_contracts.py --contracts-root ../scenara-contracts
python scripts/repository_gate.py
python scripts/production_gate.py
python -m pytest tests/test_operations.py
python -m pytest
cd frontend/data-console
npm install
npm run build
npm run typecheck
set SCENARA_DATA_POSTGRES_PASSWORD=local-test-password
set SCENARA_DATA_MINIO_ROOT_PASSWORD=local-test-password
set SCENARA_DATA_TRUSTED_SERVICE_TOKEN=local-test-service-token
set SCENARA_DATA_CORE_EVENT_ENDPOINT=http://host.docker.internal:18080/internal/v1/data/events
set SCENARA_DATA_CORE_EVENT_TOKEN=local-test-event-token
docker compose -f deploy/compose.yml up -d --wait postgres redis minio
docker compose -f deploy/compose.yml run --rm minio-init
docker compose -f deploy/compose.yml run --rm data-migrate
set SCENARA_RUN_INTEGRATION=1
python -m pytest -m integration tests/test_integration_services.py
```

前端联调至少应验证以下核心请求：`/internal/v1/datasets?limit=100`、`/internal/v1/samples?limit=100` 以及数据集版本列表接口均应正常返回成功；当客户端发送 `limit=200` 时必须返回 `422` 校验错误，以确认客户端严格遵守分页上限契约。浏览器端界面验收应重点检查：总览页面在业务列表请求失败时仍能正确显示后端的就绪状态；在 `390px` 窄屏宽度下，确认顶部设置入口、导航栏、状态卡片、密集表单和数据表格区域均无遮挡、布局错位或无意的横向溢出问题。

契约测试文件 `tests/test_contracts.py` 会在本地存在 `../scenara-contracts` 仓库时，自动校验已发布的难例交接（`hard-sample-handoff`）与数据集版本输入（`dataset-version-input`）的 JSON Schema 模式定义、示例文件以及清单 SHA-256 摘要。

本机环境已运行真实的 PostgreSQL、Redis 或 MinIO 实例时，可以直接配置环境变量覆盖连接参数：`SCENARA_DATA_INTEGRATION_DATABASE_URL`、`SCENARA_DATA_INTEGRATION_REDIS_URL`、`SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL`、`SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID` 以及 `SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY`；集成测试用例会自动确保所需的存储桶创建就绪。

集成回归必须覆盖 PostgreSQL 中 `published -> archived`、迁移包恢复已发布版本成员关系以及 `train/validation/test/query/gallery` 五种 split，避免内存适配器掩盖数据库触发器/约束差异。

在进入“已合格（`qualified`）”状态前，必须持续保留真实 PostgreSQL、Redis、S3 云服务提供方的集成测试、容量压测、容灾恢复和跨仓库端到端测试证据；在进入“生产就绪（`production_ready`）”状态前，还必须完成全面的安全渗透、合规许可、正式发布和切流演练证据。

对本地预生产演练，至少保留以下输出文件：`backup_postgres.py` 的 dump 和 manifest、`backup_object_store.py` 的对象快照清单、`verify_object_inventory.py` 的 JSON 输出、`load_test_api.py` 的延迟报告、`preproduction_check.py` 的就绪报告，以及 `rebuild_outbox.py` 的 dry-run/applied 输出。报告不得包含数据库 URL 密码、Bearer 令牌或上下文签名密钥。
