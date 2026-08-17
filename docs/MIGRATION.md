# Core 平台数据能力拆分与迁移

责任团队：景枢数据。迁移提供方：景枢 Core 平台。当前状态：计划已定义，尚未执行生产迁移。

## 顺序

1. 在契约仓库固定目标领域模型、`HardSampleManifest` 输入和 `DatasetVersionReference` 输出。
2. Core 平台建立 `DataPlatformClient`，现有本地实现作为有退出条件的兼容适配器。
3. 建设数据平台独立数据库、对象存储、身份透传和审计回传。
4. 全量迁移并核对数据集、版本、样本和标注的数量、摘要与血缘。
5. 影子读对比，完成短时冻结或基于 Outbox/CDC 的增量同步。
6. Core 平台切换到远程数据客户端，旧表进入只读观察。
7. 回滚窗口结束后退役旧写路径，禁止长期双写。

## 执行方式

Core 平台导出使用 [export_data_migration.py](/abs/path/D:/project/scenara/scripts/export_data_migration.py)，数据平台导入使用 [import_data_migration.py](/abs/path/D:/project/scenara-data/scripts/import_data_migration.py)。当前导入入口保持为离线命令行工具，避免暴露一个接收任意宿主机路径的 HTTP 导入接口；迁移包作用域、摘要、记录数和终态幂等都由导入器在本地逐项校验。

## 回滚

切换前保留 Core 平台原写路径和只读快照。发生数量、摘要、权限、审计或延迟门禁失败时，停止增量消费，将 Core 路由恢复到旧适配器，并按事件游标记录待重放范围。不得在回滚时重编码业务 ID、修改状态名或覆盖已发布版本。

退出窗口前必须证明版本标识不变、清单摘要不变或存在可验证映射、权限不扩大、审计可查询且样本内容不可变。
