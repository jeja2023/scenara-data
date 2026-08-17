"""迁移包读取适配器（指南 13）。

`FilesystemMigrationPackage` 从目录读取 Core 导出的迁移包；`InMemoryMigrationPackage` 供
单元测试与演练使用。两者都拒绝目录穿越和包外路径。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def _validate_name(name: str) -> str:
    parts = name.split("/")
    if (
        not name
        or name.startswith(("/", "\\"))
        or "\\" in name
        or ":" in name
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"迁移包包含不安全条目：{name}")
    return name


class FilesystemMigrationPackage:
    """只读目录形式的迁移包。"""

    def __init__(self, root: Path) -> None:
        resolved = Path(root).resolve()
        if not resolved.is_dir():
            raise NotADirectoryError(f"未找到迁移包目录：{resolved}")
        self._root = resolved

    @property
    def package_name(self) -> str:
        return self._root.name

    @property
    def root(self) -> Path:
        return self._root

    def names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                str(path.relative_to(self._root)).replace("\\", "/")
                for path in self._root.rglob("*")
                if path.is_file()
            )
        )

    def exists(self, name: str) -> bool:
        try:
            return self._resolve(name).is_file()
        except ValueError:
            return False

    def read(self, name: str) -> bytes:
        path = self._resolve(name)
        if not path.is_file():
            raise FileNotFoundError(f"{self.package_name}/{name}")
        return path.read_bytes()

    def _resolve(self, name: str) -> Path:
        candidate = (self._root / _validate_name(name)).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError(f"迁移包条目越过包根目录：{name}")
        return candidate


class InMemoryMigrationPackage:
    """内存迁移包，用于导入器单元测试与回滚演练。"""

    def __init__(self, files: Mapping[str, bytes], *, package_name: str = "scenara-data-migration-test") -> None:
        self._files = {_validate_name(key): value for key, value in files.items()}
        self._package_name = package_name

    @property
    def package_name(self) -> str:
        return self._package_name

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def exists(self, name: str) -> bool:
        return name in self._files

    def read(self, name: str) -> bytes:
        try:
            return self._files[_validate_name(name)]
        except KeyError as exc:
            raise FileNotFoundError(f"{self._package_name}/{name}") from exc
