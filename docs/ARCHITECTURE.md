# 架构说明

Data 拥有 Dataset、Dataset Version、Sample、Annotation、Data Quality、Data Lineage、Hard Sample 和 Dataset Builder。Core 保持 Media、Run、Result、Person、Track、Feature 和 Feedback 的事实所有权；Model 只消费已发布 Dataset Version。

依赖方向为 `scenara-data -> 已发布 scenara-contracts`。与 Core/Model 的通信只通过版本化 API、事件、不可变 Manifest 和对象引用，不共享源码或数据库表。

服务采用领域、端口、适配器分层：

```text
api -> domain -> ports <- adapters
```

第一阶段基础设施边界为 PostgreSQL 逻辑库 `scenara_data`、Redis 逻辑库 1，以及 S3-compatible Provider 的 `scenara-datasets`、`scenara-artifacts` 和 `scenara-backups` 桶。业务层不得判断具体 Provider。
