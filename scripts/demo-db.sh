#!/usr/bin/env bash
# Build a throwaway demo database (news_insight_demo) with real collected items for UI review.
# It never touches the main news_insight database. Usage: scripts/demo-db.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_URL="postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_demo"

docker compose -f "$ROOT/compose.yaml" -f "$ROOT/compose.override.yaml" exec -T postgres \
  psql -q -U news -d postgres \
  -c "DROP DATABASE IF EXISTS news_insight_demo" -c "CREATE DATABASE news_insight_demo"

cd "$ROOT/apps/api"
export DATABASE_URL="$DEMO_URL"
uv run alembic upgrade head
uv run news-insight sources seed
uv run python - <<'PY'
"""Demo only: lift a sample of sources to V3 and collect them twice (12 h ago and now)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import ValidationStage
from news_insight.sources.models import Source


class AllowAll:
    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        return True


COLLECT = [
    # news
    "etnews", "bloter", "thelec", "aitimes", "robotnews", "samsung-newsroom-kr",
    "the-verge", "ars-technica", "techcrunch", "ieee-spectrum", "android-authority", "google-blog",
    "itmedia-news", "pc-watch", "ithome-tw", "technews-tw", "heise", "computerbase",
    # community
    "geeknews", "hacker-news", "hn-on-device-ai", "hn-smartphone", "hn-robotics",
    "devto-android", "qiita-popular", "zenn-trend", "v2ex", "linuxfr",
    # research
    "arxiv-cs-ai", "arxiv-cs-ro", "arxiv-cs-hc", "nature-electronics", "europepmc-wearable-sensor",
    # oss (no token configured -> shows the config_error / paused path)
    "github-on-device-ai", "github-smart-home",
]
LADDER = {"V1": ["eu-digital-strategy", "fraunhofer-press"], "V2": ["sifted", "36kr", "publickey"]}

now = datetime.now(UTC)
with session_scope() as session, SafeFetcher.from_settings(get_settings()) as fetcher:
    for stage, keys in LADDER.items():
        for source in session.scalars(select(Source).where(Source.key.in_(keys))):
            source.validation_stage = ValidationStage(stage)
    sources = list(session.scalars(select(Source).where(Source.key.in_(COLLECT))))
    for source in sources:
        source.validation_stage = ValidationStage.V3
    for moment in (now - timedelta(hours=12), now):
        for source in sources:
            run = collect_source(session, source, fetcher=fetcher, limiter=AllowAll(), now=moment)
            print(f"{source.key:<28} {run.outcome.value:<14} new={run.items_new}")
        session.commit()
PY
echo "demo database ready: $DEMO_URL"
