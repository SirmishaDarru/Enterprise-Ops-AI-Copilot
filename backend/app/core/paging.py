import base64
import binascii
import json
import uuid
from datetime import datetime

from sqlalchemy import and_, or_

from app.core.errors import ApiError


def parse_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        if len(raw) > 200:
            raise ValueError
        time, identifier = json.loads(raw)
        parsed = datetime.fromisoformat(time)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed, uuid.UUID(identifier)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        raise ApiError(400, "INVALID_CURSOR", "Invalid pagination cursor") from None


def after_cursor(time_column, id_column, cursor: str | None):
    parsed = parse_cursor(cursor)
    if parsed is None:
        return None
    time, identifier = parsed
    return or_(time_column < time, and_(time_column == time, id_column < identifier))


def page(items: list, limit: int, time_attr: str) -> tuple[list, str | None]:
    has_more = len(items) > limit
    selected = items[:limit]
    if not has_more:
        return selected, None
    last = selected[-1]
    data = json.dumps([getattr(last, time_attr).isoformat(), str(last.id)]).encode()
    return selected, base64.urlsafe_b64encode(data).decode().rstrip("=")
