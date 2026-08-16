# Core 数据能力拆分与迁移

责任团队：Scenara Data。迁移提供方：Scenara Core。当前状态：计划已定义，尚未执行生产迁移。

## 顺序

1. 在 Contracts 固定目标领域模型、HardSampleManifest 输入和 DatasetVersionReference 输出。
2. Core 建立 DataPlatformClient，现有本地实现作为有退出条件的兼容 Adapter。
3. 建设 Data 独立数据库、对象存储、IAM 透传和审计回传。
4. 全量迁移并核对 Dataset、Version、Sample、Annotation 数量、摘要和血缘。
5. 影子读对比，完成短时冻结或基于 Outbox/CDC 的增量同步。
6. Core 切换到远程 Data Client，旧表进入只读观察。
7. 回滚窗口结束后退役旧写路径，禁止长期双写。

## 执行方式

Core 导出使用 [export_data_migration.py](/abs/path/D:/project/scenara/scripts/export_data_migration.py)，Data 导入使用 [import_data_migration.py](/abs/path/D:/project/scenara-data/scripts/import_data_migration.py)。当前导入入口保持为离线 CLI，避免暴露一个接收任意宿主机路径的 HTTP 导入接口；迁移包作用域、摘要、记录数和终态幂等都由导入器在本地逐项校验。

## 回滚

切换前保留 Core 原写路径和只读快照。发生数量、摘要、权限、审计或延迟门禁失败时，停止增量消费，将 Core 路由恢复到旧 Adapter，并按事件游标记录待重放范围。不得在回滚时重编码业务 ID、修改状态名或覆盖已发布版本。

退出窗口前必须证明版本标识不变、Manifest 摘要不变或存在可验证映射、权限不扩大、审计可查询且样本内容不可变。
