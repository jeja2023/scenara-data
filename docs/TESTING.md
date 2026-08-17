# 测试文档

当前门禁覆盖领域状态机、不可变对象引用、RFC 3339 探针、身份/权限、租户隔离、幂等、数据集发布、质量、Outbox、迁移、仓库必需文件、正式契约版本/摘要锁定、已发布模式/示例校验，以及禁止跨仓库源码导入。`0.1.4` 另增加独立工作台中文化、分页契约和移动端布局的验收要求。

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

前端联调至少应验证以下请求：`/internal/v1/datasets?limit=100`、`/internal/v1/samples?limit=100` 和数据集版本列表均返回成功；发送 `limit=200` 应返回 `422`，以确认客户端遵守分页上限。浏览器验收应检查总览在业务列表失败时仍能正确显示后端就绪状态，并在 `390px` 宽度下确认顶部设置入口、导航、状态卡、密集表单和表格区域没有遮挡或无意横向溢出。

`tests/test_contracts.py` 会在本地存在 `../scenara-contracts` 时校验已发布 `hard-sample-handoff` 与 `dataset-version-input` 的模式、示例和清单摘要。

本机已有 PostgreSQL/Redis/MinIO 时，也可以直接覆盖 `SCENARA_DATA_INTEGRATION_DATABASE_URL`、`SCENARA_DATA_INTEGRATION_REDIS_URL`、`SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL`、`SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID` 和 `SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY` 来复用现有服务；`integration` 用例会自行确保所需桶存在。

进入 `qualified` 前仍需持续保留真实 PostgreSQL、Redis、S3 提供方集成、容量、恢复和跨仓库端到端测试；进入 `production_ready` 前还需完成安全、许可、发布和切流证据。
