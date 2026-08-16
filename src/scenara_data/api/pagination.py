from __future__ import annotations

import base64
import binascii

from scenara_data.application.errors import InputValidationError


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        value = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        offset = int(value)
    except (UnicodeError, ValueError, binascii.Error) as exc:
        raise InputValidationError("分页游标无效") from exc
    if offset < 0:
        raise InputValidationError("分页游标无效")
    return offset


def encode_cursor(offset: int, limit: int, total: int) -> str | None:
    next_offset = offset + limit
    if next_offset >= total:
        return None
    return base64.urlsafe_b64encode(str(next_offset).encode("ascii")).decode("ascii")
