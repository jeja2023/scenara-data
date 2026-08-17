"""内存表：带租户/项目作用域与唯一约束的开发存储原语。

内存适配器只用于开发与单元测试，永远不是生产事实存储。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

Scope = tuple[str, str]


@dataclass(slots=True)
class Table[T]:
    """按主键存储、按 `(tenant_id, project_id)` 作用域隔离的行集合。"""

    name: str
    key: Callable[[T], str]
    unique: tuple[Callable[[T], tuple[Any, ...]], ...] = ()
    rows: dict[str, T] = field(default_factory=dict)
    scopes: dict[str, Scope] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def add(self, value: T, scope: Scope) -> None:
        identity = self.key(value)
        with self.lock:
            if identity in self.rows:
                raise ValueError(f"{self.name} 主键重复：{identity}")
            for extractor in self.unique:
                candidate = extractor(value)
                for existing in self.rows.values():
                    if extractor(existing) == candidate:
                        raise ValueError(f"{self.name} 唯一键重复：{candidate}")
            self.rows[identity] = value
            self.scopes[identity] = scope

    def get(self, identity: str, scope: Scope) -> T:
        with self.lock:
            value = self.rows.get(identity)
            if value is None or self.scopes.get(identity) != scope:
                raise KeyError(identity)
            return value

    def find(self, identity: str, scope: Scope) -> T | None:
        try:
            return self.get(identity, scope)
        except KeyError:
            return None

    def update(self, value: T) -> None:
        identity = self.key(value)
        with self.lock:
            if identity not in self.rows:
                raise KeyError(identity)
            self.rows[identity] = value

    def scope_of(self, identity: str) -> Scope | None:
        return self.scopes.get(identity)

    def all_in_scope(self, scope: Scope) -> list[T]:
        with self.lock:
            return [value for identity, value in self.rows.items() if self.scopes.get(identity) == scope]

    def select(
        self,
        scope: Scope,
        *,
        predicate: Callable[[T], bool] | None = None,
        sort_key: Callable[[T], Any] | None = None,
        reverse: bool = False,
    ) -> list[T]:
        values = [value for value in self.all_in_scope(scope) if predicate is None or predicate(value)]
        if sort_key is not None:
            values.sort(key=sort_key, reverse=reverse)
        return values

    def page(
        self,
        scope: Scope,
        *,
        limit: int,
        offset: int,
        predicate: Callable[[T], bool] | None = None,
        sort_key: Callable[[T], Any] | None = None,
        reverse: bool = True,
    ) -> tuple[list[T], int]:
        values = self.select(scope, predicate=predicate, sort_key=sort_key, reverse=reverse)
        return values[offset : offset + limit], len(values)


def paginate[T](values: Iterable[T], *, limit: int, offset: int) -> tuple[list[T], int]:
    materialized = list(values)
    return materialized[offset : offset + limit], len(materialized)
