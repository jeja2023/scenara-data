# 测试文档

当前门禁覆盖领域状态机、不可变对象引用、RFC 3339 探针、身份/权限、租户隔离、幂等、Dataset 发布、质量、Outbox、迁移、仓库必需文件、正式契约版本/摘要锁定、已发布 schema/example 校验，以及禁止跨仓库源码导入。

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

`tests/test_contracts.py` 会在本地存在 `../scenara-contracts` 时校验已发布 `hard-sample-handoff` 与 `dataset-version-input` 的 schema、example 和 manifest 摘要。

本机已有 PostgreSQL/Redis/MinIO 时，也可以直接覆盖 `SCENARA_DATA_INTEGRATION_DATABASE_URL`、`SCENARA_DATA_INTEGRATION_REDIS_URL`、`SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL`、`SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID` 和 `SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY` 来复用现有服务；`integration` 用例会自行确保所需桶存在。

进入 `qualified` 前仍需持续保留真实 PostgreSQL、Redis、S3 Provider 集成、容量、恢复和跨仓库端到端测试；进入 `production_ready` 前还需完成安全、许可、发布和切流证据。
