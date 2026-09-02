# 测试与质量门禁规范

当前仓库门禁全面覆盖领域状态机、不可变对象引用、UTC RFC 3339 时间探针、身份鉴权与权限隔离、多租户多项目隔离、写操作幂等控制、数据集版本发布不可变性、数据质量检验、发件箱事件投递、数据库迁移、必需架构文档完整性、正式契约版本与哈希摘要锁定、多领域标注模式与示例校验，以及严禁跨仓库源码导入规则。`0.1.6` 版本重点补充了 OCR 文本识别、行为姿态动作、服饰属性等多领域标注语义与难例回归测试。

```powershell
python -m ruff check src scripts tests
python scripts/validate_repository_contracts.py --contracts-root ../scenara-contracts
python scripts/repository_gate.py
python -m pytest
cd frontend/data-console
npm install
npm run build
npm run typecheck
docker compose -f deploy/compose.yml up -d --wait postgres redis minio
docker compose -f deploy/compose.yml run --rm minio-init
docker compose -f deploy/compose.yml run --rm data-migrate
set SCENARA_RUN_INTEGRATION=1
python -m pytest -m integration tests/test_integration_services.py
```

前端联调至少应验证以下核心请求：`/internal/v1/datasets?limit=100`、`/internal/v1/samples?limit=100` 以及数据集版本列表接口均应正常返回成功；当客户端发送 `limit=200` 时必须返回 `422` 校验错误，以确认客户端严格遵守分页上限契约。浏览器端界面验收应重点检查：总览页面在业务列表请求失败时仍能正确显示后端的就绪状态；在 `390px` 窄屏宽度下，确认顶部设置入口、导航栏、状态卡片、密集表单和数据表格区域均无遮挡、布局错位或无意的横向溢出问题。

契约测试文件 `tests/test_contracts.py` 会在本地存在 `../scenara-contracts` 仓库时，自动校验已发布的难例交接（`hard-sample-handoff`）与数据集版本输入（`dataset-version-input`）的 JSON Schema 模式定义、示例文件以及清单 SHA-256 摘要。

本机环境已运行真实的 PostgreSQL、Redis 或 MinIO 实例时，可以直接配置环境变量覆盖连接参数：`SCENARA_DATA_INTEGRATION_DATABASE_URL`、`SCENARA_DATA_INTEGRATION_REDIS_URL`、`SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL`、`SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID` 以及 `SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY`；集成测试用例会自动确保所需的存储桶创建就绪。

在进入“已合格（`qualified`）”状态前，必须持续保留真实 PostgreSQL、Redis、S3 云服务提供方的集成测试、容量压测、容灾恢复和跨仓库端到端测试证据；在进入“生产就绪（`production_ready`）”状态前，还必须完成全面的安全渗透、合规许可、正式发布和切流演练证据。
