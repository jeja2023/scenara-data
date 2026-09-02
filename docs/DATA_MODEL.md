# 数据模型文档

- **数据集（Dataset）**：租户/项目内的数据集聚合根。
- **数据集版本（Dataset Version）**：不可变发布单元，状态流转为：`草稿（draft） -> 构建中（building） -> 就绪（ready） -> 已发布（published） -> 已归档（archived）`，构建失败进入 `失败（failed）`。
- **样本（Sample）**：通过对象引用关联来源内容和血缘，不保存核心平台（Core）本地文件路径。
- **标注（Annotation）**：绑定样本、标注模式、操作者、状态和审计快照。
- **数据集清单（Dataset Manifest）**：记录唯一的样本 ID、数据分割计数、对象引用和 SHA-256 哈希摘要。

发布后的数据集版本不允许修改清单或样本内容。修改数据必须创建新版本。跨仓库输出使用数据集版本引用契约（`DatasetVersionReference` `1.2.0`），难例输入使用难例清单契约（`HardSampleManifest` `1.2.0`）。所有跨仓时间字段统一使用以 `Z` 结尾的 UTC RFC3339 字符串，严禁使用数值 Unix 时间戳。

领域标注模式来自契约仓库领域标注集合（`domain-annotations` `1.1.0`），数据平台只消费按摘要锁定的不可变制品。当前登记了人体检测（`scenara.portrait.detection.v1`）、布控误报复核（`scenara.portrait.surveillance-review.v1`）、OCR 文档识别（`scenara.ocr.document.v1`）、行为动作识别（`scenara.behavior.action.v1`）、服饰风格检测（`scenara.fashion.style.v1`）以及历史难例兼容模式（`scenara.feedback.correction.v1`）；未知模式标识（Schema ID）、媒体类型不匹配、布控复核缺少告警/处置字段、行为结束时间早于开始时间、重复 OCR 阅读顺序或空服饰标签都会触发校验失败并安全关闭。
