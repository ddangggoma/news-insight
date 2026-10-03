"""Date macros in endpoint URLs and queries: {today}, {today-30d}, {today-180d} (KST dates)."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MACRO = re.compile(r"\{today(?:-(\d{1,4})d)?\}")
KST = ZoneInfo("Asia/Seoul")


def expand_macros(template: str, *, now: datetime) -> str:
    today = now.astimezone(KST).date()

    def replace(match: re.Match[str]) -> str:
        return (today - timedelta(days=int(match.group(1) or 0))).isoformat()

    return MACRO.sub(replace, template)
