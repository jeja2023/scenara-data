# 景枢数据

`scenara-data` 是景枢数据平台责任仓库，负责数据资产、样本、数据集、不可变数据集版本、标注、数据质量、数据血缘、难例和数据集构建。它不负责模型训练、生产推理、共享身份与访问管理、统一控制台或 API 网关。

- 当前版本：`0.1.5`
- 当前成熟度：`implemented`
- 责任团队：景枢数据
- 规范来源：`景枢平台总体开发规范.md` `1.3.0`

当前实现已建立领域模型、状态机、内存与 PostgreSQL/S3/Redis 适配器、正式内部数据集 API、迁移导入命令行工具、事件 Outbox 工作进程、独立 Vue 数据工作台、身份权限、审计、正式契约门禁、跨仓库端到端测试和自动化测试。`0.1.5` 进一步完成四仓库规范审计、未完成任务计划、迁移导入验收和版本/契约文档同步。真实基础设施资格、容量、恢复和更完整的生产证据仍未完成，因此不得标记为 `production_ready`。

剩余任务和生产资格前置条件见 [剩余任务计划](docs/REMAINING_TASK_PLAN.md)。

## 边界

- 训练输入只发布不可变数据集版本引用，不向模型平台暴露本地路径或数据库表。
- 通过 `hard-sample-handoff` 接收 Core 平台已批准、已授权、已脱敏的难例清单。
- 通过 `dataset-version-input` 向模型平台发布版本、血缘、授权和清单摘要。
- 用户、组织、项目、角色和 API 密钥由 `scenara` 统一管理；数据平台只验证透传身份和权限。
- 用户界面由 `scenara` 提供统一控制台门户和导航壳，本仓库可以建设独立前端，但必须遵循统一设计系统、主题令牌和门户接入规范。

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

数据平台前端位于 `frontend/data-console`，当前工作台版本为 `0.1.5`。页面包括总览、数据集、版本治理、难例导入和运维探针，面向用户的页面文本、状态标签、错误提示和设置表单均使用中文；协议字段、资源 ID、模型 ID、媒体类型和路径仍保留其机器可读形式。开发时先在仓库根目录启动后端，再在前端目录启动 Vite：

```powershell
cd frontend/data-console
npm install
set VITE_DATA_API_BASE=http://127.0.0.1:8082
npm run dev
```

如果后端端口不是 `8082`，把 `VITE_DATA_API_BASE` 改成实际地址即可。前端会通过统一设计系统、主题令牌和门户规范保持与 Core 平台和模型平台一致的视觉语言。

工作台访问业务页面前会进入登录页。本地默认用户名为 `admin`；密码默认复用后端 `SCENARA_DATA_TRUSTED_SERVICE_TOKEN`，内存开发模式未配置时为 `scenara-data-dev-token`。如需为工作台单独设置密码，可配置 `SCENARA_DATA_CONSOLE_PASSWORD`，并可通过 `SCENARA_DATA_CONSOLE_TENANT_ID`、`SCENARA_DATA_CONSOLE_PROJECT_ID` 固定登录后的租户和项目。

工作台列表请求遵循后端分页契约，默认使用 `limit=100`。总览和运维页分别处理就绪探针、健康探针与业务列表失败，单个业务请求失败不会把可访问的后端显示为“离线”。移动端验收重点包括顶部连接状态和设置入口、导航抽屉、密集表单换行、表格横向滚动以及错误/空状态展示。
