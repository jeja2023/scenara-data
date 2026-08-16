# Scenara Data

`scenara-data` 是景枢数据平台责任仓库，负责数据资产、样本、Dataset、不可变 Dataset Version、Annotation、Data Quality、Data Lineage、Hard Sample 和 Dataset Builder。它不负责模型训练、生产推理、共享 IAM、统一 Console 或 API 网关。

- 当前版本：`0.1.3`
- 当前成熟度：`implemented`
- 责任团队：Scenara Data
- 规范来源：`景枢平台总体开发规范.md` `1.3.0`

当前实现已建立领域模型、状态机、内存与 PostgreSQL/S3/Redis 适配器、正式内部 Dataset API、迁移导入 CLI、事件 Outbox Worker、独立 Vue 数据工作台、身份权限、审计、正式契约门禁、跨仓库 E2E 和自动化测试。真实基础设施资格、容量、恢复和更完整的生产证据仍未完成，因此不得标记为 `production_ready`。

## 边界

- 训练输入只发布不可变 Dataset Version 引用，不向模型平台暴露本地路径或数据库表。
- 通过 `hard-sample-handoff` 接收 Core 已批准、已授权、已脱敏的难例清单。
- 通过 `dataset-version-input` 向 Model 发布版本、血缘、授权和 Manifest 摘要。
- 用户、组织、项目、角色和 API Key 由 `scenara` 统一管理；Data 只验证透传身份和权限。
- 用户界面由 `scenara` 提供统一 Console 门户和导航壳，本仓库可以建设独立前端，但必须遵循统一设计系统、主题令牌和门户接入规范。

## 本地验证

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src scripts tests
python scripts/repository_gate.py
python -m pytest
python start.py --reload
uvicorn scenara_data.api.app:app --host 127.0.0.1 --port 8081
```

`start.py` 支持三种模式：`all`（后端 + 前端）、`backend`、`frontend`。它会在启动前检查本机 PostgreSQL、Redis 和 MinIO 是否可连，并为开发态自动补齐 `SCENARA_DATA_CORE_EVENT_ENDPOINT` 与 `SCENARA_DATA_CORE_EVENT_TOKEN`；如果默认端口被占用，它会自动切换到下一个可用端口并提示你。若需覆盖默认探测地址，可设置 `SCENARA_DATA_INTEGRATION_DATABASE_URL`、`SCENARA_DATA_INTEGRATION_REDIS_URL`、`SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL`、`SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID` 和 `SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY`。

```powershell
python start.py --mode all
cd frontend/data-console
npm install
npm run dev
```

健康检查：`GET http://127.0.0.1:8081/health`。正式业务 API 必须先在 `scenara-contracts` 发布契约，当前未把内部领域模型声明为公共接口。

### 前端工作台

Data 平台前端位于 `frontend/data-console`。开发时先在仓库根目录启动后端，再在前端目录启动 Vite：

```powershell
cd frontend/data-console
npm install
set VITE_DATA_API_BASE=http://127.0.0.1:8082
npm run dev
```

如果后端端口不是 `8082`，把 `VITE_DATA_API_BASE` 改成实际地址即可。前端会通过统一设计系统、主题令牌和门户规范保持与 Core / Model 一致的视觉语言。
