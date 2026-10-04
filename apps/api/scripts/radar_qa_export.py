"""Export radar responses from the seeded demo corpus for the signal regression (checklist QA-1).

Usage (the database name must contain "demo"):
    RADAR_DEMO_NOW=2026-10-04T15:00:00+00:00 DATABASE_URL=...news_insight_qa_demo \\
        uv run python scripts/radar_qa_export.py <out_dir>
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.public import radar as radar_queries
from news_insight.public.filters import ReaderFilters
from news_insight.public.periods import calendar_window, current_key

# the closed windows around the pinned RADAR_DEMO_NOW used by scripts/dev.sh radar-qa
VIEWS = [("week", "2026-W40"), ("week", "2026-W39"), ("month", "2026-09"), ("quarter", "2026-Q3")]


def main() -> None:
    if "demo" not in (make_url(get_settings().database_url).database or ""):
        raise SystemExit("refusing: use a database whose name contains 'demo'")
    now = datetime.fromisoformat(os.environ["RADAR_DEMO_NOW"])
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with session_scope() as session:
        for kind, key in VIEWS:
            window = calendar_window(kind, key)
            body = radar_queries.radar(
                session,
                ReaderFilters.build(scope="relevant", q=None),
                window,
                current_key(kind, now),
                now,
            )
            (out / f"{kind}-{key}.json").write_text(body.model_dump_json(), encoding="utf-8")
            print(f"exported {kind} {key}: themes={len(body.themes)} keywords={len(body.keywords)}")


if __name__ == "__main__":
    main()
