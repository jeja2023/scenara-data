# 数据模型文档

- 数据集：租户/项目内的数据集聚合根。
- 数据集版本：不可变发布单元，状态为 `draft -> building -> ready -> published -> archived`，构建失败进入 `failed`。
- 样本：通过对象引用关联来源内容和血缘，不保存 Core 平台本地路径。
- 标注：绑定样本、标注模式、操作者、状态和审计。
- 数据集清单：记录唯一的样本 ID、数据分割计数、对象引用和 SHA-256。

发布后的数据集版本不允许修改清单或样本内容。修改数据必须创建新版本。跨仓库输出使用 `DatasetVersionReference` `1.2.0`，难例输入使用 `HardSampleManifest` `1.2.0`。所有跨仓时间字段统一使用以 `Z` 结尾的 UTC RFC3339 字符串，禁止数值 Unix 时间戳。

领域标注模式来自 Contracts `domain-annotations` `1.1.0`，Data 只消费按摘要锁定的不可变制品。当前登记 `scenara.portrait.detection.v1`、`scenara.portrait.surveillance-review.v1`、`scenara.ocr.document.v1`、`scenara.behavior.action.v1`、`scenara.fashion.style.v1` 以及历史难例兼容模式 `scenara.feedback.correction.v1`；未知 Schema ID、媒体类型不匹配、布控复核缺少告警/处置字段、行为结束时间早于开始时间、重复 OCR 阅读顺序或空服饰标签都会失败关闭。
