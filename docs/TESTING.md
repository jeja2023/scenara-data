# 测试文档

当前门禁覆盖领域状态机、不可变对象引用、RFC 3339 健康探针、仓库必需文件、契约版本/摘要锁定和禁止跨仓库源码导入。

```powershell
python -m ruff check src scripts tests
python scripts/repository_gate.py
python -m pytest
```

进入 `implemented` 前还需补充 PostgreSQL、Redis、S3 Provider 适配器测试、权限/幂等/API 测试和迁移测试。进入 `qualified` 前必须完成真实基础设施集成、容量、恢复和跨仓库端到端测试。
