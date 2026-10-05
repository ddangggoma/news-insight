"""Field helpers for mapped records (JSON APIs and declarative HTML)."""

from datetime import UTC, datetime, tzinfo
from email.utils import parsedate_to_datetime
from typing import Any

DATE_FORMATS = (
    "%Y.%m.%d",
    "%Y/%m/%d",
    "%Y.%m.%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y.%m.%d. %H:%M",
    "%Y%m%d",
)
EPOCH_MS_THRESHOLD = 10**11


def dotted_get(value: Any, path: str) -> Any:
    if not path:
        return value
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def parse_datetime(value: Any, *, assume_tz: tzinfo = UTC) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, list | tuple):
        if len(value) != 3 or any(type(part) is not int for part in value):
            return None  # partial dates are unknown; never invent a day or month
        try:
            return datetime(value[0], value[1], value[2], tzinfo=assume_tz).astimezone(UTC)
        except ValueError:
            return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > EPOCH_MS_THRESHOLD else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    text = str(value).strip()
    parsed = _parse_text(text) if text else None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=assume_tz)
    return parsed.astimezone(UTC)


def _parse_text(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None


def text_or_none(value: Any) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None
    text = str(value).strip()
    return text or None
