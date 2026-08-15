# Scenara Data

`scenara-data` 是景枢数据平台责任仓库，负责数据资产、样本、Dataset、不可变 Dataset Version、Annotation、Data Quality、Data Lineage、Hard Sample 和 Dataset Builder。它不负责模型训练、生产推理、共享 IAM、统一 Console 或 API 网关。

- 当前版本：`0.1.0`
- 当前成熟度：`seed`
- 责任团队：Scenara Data
- 规范来源：`景枢平台总体开发规范.md` `1.2.1`

当前初搭已建立领域模型、状态机、端口、运行探针、测试、CI、契约锁定以及拆分/迁移/恢复/安全门禁。业务数据库适配器、正式 Dataset API、历史数据迁移和跨仓库端到端测试尚未完成，因此不得标记为 `production_ready`。

## 边界

- 训练输入只发布不可变 Dataset Version 引用，不向模型平台暴露本地路径或数据库表。
- 通过 `hard-sample-handoff` 接收 Core 已批准、已授权、已脱敏的难例清单。
- 通过 `dataset-version-input` 向 Model 发布版本、血缘、授权和 Manifest 摘要。
- 用户、组织、项目、角色和 API Key 由 `scenara` 统一管理；Data 只验证透传身份和权限。
- 用户界面由 `scenara` 统一 Console 提供，本仓库不建设独立前端。

## 本地验证

```powershell
python -m pip install -e ".[dev]"
python -m ruff check src scripts tests
python scripts/repository_gate.py
python -m pytest
uvicorn scenara_data.api.app:app --host 127.0.0.1 --port 8081
```

健康检查：`GET http://127.0.0.1:8081/health`。正式业务 API 必须先在 `scenara-contracts` 发布契约，当前未把内部领域模型声明为公共接口。
