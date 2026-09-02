# 架构说明

数据平台拥有数据集、数据集版本、样本、标注、数据质量、数据血缘、难例和数据集构建能力。核心平台（Core）保持媒体、运行、结果、人员、轨迹、特征和反馈的事实所有权；模型平台（Model）只消费已发布的数据集版本。

依赖方向为：`景枢数据平台（scenara-data） -> 已发布契约仓库（scenara-contracts）`。与核心平台和模型平台的通信只通过版本化 API、事件、不可变清单和对象引用，严禁共享源码或数据库表。

服务采用领域、端口、适配器分层架构：

```text
接口层（api） -> 领域层（domain） -> 端口层（ports） <- 适配器层（adapters）
```

第一阶段基础设施边界为 PostgreSQL 逻辑库 `scenara_data`、Redis 逻辑库 1，以及兼容 S3 的对象存储提供方所管理的 `scenara-datasets`（数据集桶）、`scenara-artifacts`（工件桶）和 `scenara-backups`（备份桶）。业务层不得硬编码具体云服务提供方。
