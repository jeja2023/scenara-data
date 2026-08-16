from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from scenara_data.application.errors import IdempotencyConflictError, InputValidationError
from scenara_data.ports.interfaces import IdempotencyRecord, IdempotencyStore, RequestContext, UnitOfWork


def request_digest(value: Any) -> str:
    content = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class IdempotencyService:
    def __init__(self, store: IdempotencyStore, *, unit_of_work: UnitOfWork | None = None) -> None:
        self._store = store
        self._unit_of_work = unit_of_work

    def execute(
        self,
        *,
        context: RequestContext,
        operation: str,
        request_hash: str,
        status_code: int,
        callback: Callable[[], dict[str, Any]],
    ) -> tuple[int, dict[str, Any], bool]:
        if not context.idempotency_key:
            raise InputValidationError("写操作必须提供 Idempotency-Key")
        scope = ":".join(
            (context.tenant_id, context.project_id, context.principal_id, operation)
        )
        def execute_once() -> tuple[int, dict[str, Any], bool]:
            previous = self._store.get(scope, context.idempotency_key)
            if previous is not None:
                return self._replay(previous, request_hash)

            response_payload = callback()
            self._store.save(
                IdempotencyRecord(
                    scope=scope,
                    key=context.idempotency_key,
                    request_hash=request_hash,
                    status_code=status_code,
                    response_payload=response_payload,
                )
            )
            return status_code, response_payload, False

        if self._unit_of_work is None:
            return execute_once()
        try:
            with self._unit_of_work.transaction():
                return execute_once()
        except ValueError:
            # 并发请求可能同时未读到记录；唯一约束只允许一个事务提交。失败事务回滚后重读。
            previous = self._store.get(scope, context.idempotency_key)
            if previous is None:
                raise
            return self._replay(previous, request_hash)

    @staticmethod
    def _replay(previous: IdempotencyRecord, request_hash: str) -> tuple[int, dict[str, Any], bool]:
        if previous.request_hash != request_hash:
            raise IdempotencyConflictError()
        return previous.status_code, previous.response_payload, True
