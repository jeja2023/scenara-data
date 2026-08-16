"""PostgreSQL 连接、事务与 SQL 执行原语。

所有查询都必须带 `tenant_id` 与 `project_id` 作用域；禁止无作用域查询和跨租户外键
（指南 8）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

DUPLICATE_KEY_SQLSTATE = "23505"
FOREIGN_KEY_SQLSTATE = "23503"


class SqlSupport:
    """连接持有者：同一上下文内的嵌套调用复用同一连接与事务。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._active: ContextVar[Any | None] = ContextVar("scenara_data_connection", default=None)

    # ---------------------------------------------------------------- 事务

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._active.get() is not None:
            yield
            return
        with self._connect() as connection:
            token = self._active.set(connection)
            try:
                yield
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                self._active.reset(token)

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        active = self._active.get()
        if active is not None:
            yield active
            return
        with self._connect() as connection:
            yield connection
            connection.commit()

    def _connect(self) -> Any:
        import psycopg  # 延迟导入：PostgreSQL 是可选运行依赖
        from psycopg.rows import dict_row

        return psycopg.connect(self._database_url, row_factory=dict_row)

    def ping(self) -> bool:
        try:
            with self._connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None
        except Exception:
            return False

    # ------------------------------------------------------------ SQL 辅助

    def _insert(self, statement: str, parameters: tuple[Any, ...]) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            try:
                cursor.execute(statement, parameters)
            except Exception as exc:
                raise _translate(exc) from exc

    def _insert_returning_count(self, statement: str, parameters: tuple[Any, ...]) -> int:
        with self._connection() as connection, connection.cursor() as cursor:
            try:
                cursor.execute(statement, parameters)
            except Exception as exc:
                raise _translate(exc) from exc
            return int(cursor.rowcount)

    def _execute(self, statement: str, parameters: tuple[Any, ...]) -> int:
        with self._connection() as connection, connection.cursor() as cursor:
            try:
                cursor.execute(statement, parameters)
            except Exception as exc:
                raise _translate(exc) from exc
            return int(cursor.rowcount)

    def _fetch_one(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def _fetch_all(self, statement: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            return [dict(row) for row in cursor.fetchall()]

    def _fetch_page(
        self, statement: str, parameters: tuple[Any, ...], count_statement: str, count_parameters: tuple[Any, ...]
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._fetch_all(statement, parameters)
        if rows and "total" in rows[0]:
            return rows, int(rows[0]["total"])
        return rows, self._count(count_statement, count_parameters)

    def _count(self, statement: str, parameters: tuple[Any, ...]) -> int:
        row = self._fetch_one(statement, parameters)
        if row is None:
            return 0
        return int(next(iter(row.values())))

    @staticmethod
    def _json(value: Any) -> str:
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _translate(exc: Exception) -> Exception:
    """把数据库约束冲突映射为领域可处理的异常，不向上层泄漏数据库细节。"""
    sqlstate = getattr(exc, "sqlstate", None) or getattr(getattr(exc, "diag", None), "sqlstate", None)
    if sqlstate == DUPLICATE_KEY_SQLSTATE:
        return ValueError("duplicate record")
    if sqlstate == FOREIGN_KEY_SQLSTATE:
        return KeyError("referenced record not found")
    return exc
