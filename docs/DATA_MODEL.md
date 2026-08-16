# 数据模型文档

- Dataset：租户/项目内的数据集聚合根。
- Dataset Version：不可变发布单元，状态为 `draft -> building -> ready -> published -> archived`，构建失败进入 `failed`。
- Sample：通过对象引用关联来源内容和血缘，不保存 Core 本地路径。
- Annotation：绑定 Sample、标注 Schema、操作者、状态和审计。
- Dataset Manifest：记录唯一 Sample ID、split 计数、对象引用和 SHA-256。

发布后的 Dataset Version 不允许修改 Manifest 或样本内容。修改数据必须创建新版本。跨仓库输出使用 `DatasetVersionReference` `1.0.0`，输入 Hard Sample 使用 `HardSampleManifest` `1.0.0`。
