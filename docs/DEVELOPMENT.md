# 开发规范

模块按 Dataset、Version、Sample、Annotation、Quality 和 Lineage 领域划分，不建立无边界 `utils`、`common` 或 `helpers` 目录。业务逻辑依赖 Repository、Provider 和 Client 端口，适配器通过契约测试替换。

新增公共 API、事件、状态或错误码前必须先在 `scenara-contracts` 登记。所有写操作定义权限、幂等、审计和失败路径。时间使用 UTC RFC 3339，持续时间使用带单位字段，跨仓库文件使用 SHA-256 不可变对象引用。
