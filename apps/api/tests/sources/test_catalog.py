from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.presets import effective_config
from news_insight.sources.catalog import (
    DEFAULT_CATALOG_PATH,
    Catalog,
    load_catalog,
    seed_catalog,
)
from news_insight.sources.enums import (
    SourceStatus,
    Track,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source

ENTRY = """
  - key: example-news
    name: Example News
    track: news
    category: independent_media
    access_method: feed
    endpoint_url: https://www.example.com/feed.xml
    official_domain: example.com
    operator: Example Media Inc.
    region: global_en
    language: en
    poll_class: news
    dx_relevance: 모바일·가전 제품 동향을 다루는 테크 미디어
    terms_url: https://www.example.com/terms
    storage_right: excerpt_allowed
"""


def write_catalog(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(f"version: 1\nsources:{body}", encoding="utf-8")
    return path


def test_load_valid_catalog(tmp_path: Path) -> None:
    catalog = load_catalog(write_catalog(tmp_path, ENTRY))

    assert [entry.key for entry in catalog.sources] == ["example-news"]
    assert catalog.sources[0].track is Track.NEWS


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="duplicate source keys: example-news"):
        load_catalog(write_catalog(tmp_path, ENTRY + ENTRY))


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_catalog(write_catalog(tmp_path, ENTRY + "    surprise: true\n"))


def test_non_http_endpoint_is_rejected(tmp_path: Path) -> None:
    body = ENTRY.replace("https://www.example.com/feed.xml", "ftp://example.com/feed.xml")

    with pytest.raises(ValidationError, match="absolute http"):
        load_catalog(write_catalog(tmp_path, body))


def test_bundled_catalog_loads_and_covers_every_track() -> None:
    catalog = load_catalog(DEFAULT_CATALOG_PATH)

    assert {entry.track for entry in catalog.sources} == set(Track)


@pytest.mark.db
def test_seed_creates_candidates_and_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    catalog = load_catalog(write_catalog(tmp_path, ENTRY))

    first = seed_catalog(db_session, catalog)
    second = seed_catalog(db_session, catalog)

    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    assert first.created == ["example-news"]
    assert (second.created, second.updated, second.reset) == ([], [], [])
    assert source.status is SourceStatus.CANDIDATE
    assert source.validation_stage is ValidationStage.UNVERIFIED


@pytest.mark.db
def test_seed_updates_descriptive_fields_without_reset(db_session: Session, tmp_path: Path) -> None:
    seed_catalog(db_session, load_catalog(write_catalog(tmp_path, ENTRY)))
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    record_check(db_session, source, ValidationStage.V0, CheckResult(passed=True))

    renamed = ENTRY.replace("name: Example News", "name: Example News Daily")
    result = seed_catalog(db_session, load_catalog(write_catalog(tmp_path, renamed)))

    assert result.updated == ["example-news"]
    assert source.name == "Example News Daily"
    assert source.validation_stage is ValidationStage.V0


@pytest.mark.db
def test_seed_resets_validation_when_endpoint_changes(db_session: Session, tmp_path: Path) -> None:
    seed_catalog(db_session, load_catalog(write_catalog(tmp_path, ENTRY)))
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    record_check(db_session, source, ValidationStage.V0, CheckResult(passed=True))

    moved = ENTRY.replace("/feed.xml", "/rss.xml")
    result = seed_catalog(db_session, load_catalog(write_catalog(tmp_path, moved)))

    assert result.reset == ["example-news"]
    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.validation_events[-1].outcome is ValidationOutcome.RESET


def test_catalog_model_requires_version_1() -> None:
    with pytest.raises(ValidationError):
        Catalog.model_validate({"version": 2, "sources": []})


def test_unknown_preset_is_rejected(tmp_path: Path) -> None:
    body = ENTRY + "    config:\n      preset: nope\n"

    with pytest.raises(ValidationError, match="unknown preset 'nope'"):
        load_catalog(write_catalog(tmp_path, body))


def test_bundled_presets_resolve_and_github_declares_its_token() -> None:
    entries = {entry.key: entry for entry in load_catalog(DEFAULT_CATALOG_PATH).sources}

    for entry in entries.values():
        effective_config(entry.config)
    assert entries["github-on-device-ai"].config["auth"] == {"secret": "GITHUB_TOKEN"}
    assert entries["arxiv-cs-ai"].endpoint_url.startswith("https://export.arxiv.org/api/query")


def test_bundled_catalog_covers_track_targets() -> None:
    from collections import Counter

    from news_insight.sources.portfolio import TRACK_TARGETS

    counts = Counter(entry.track for entry in load_catalog(DEFAULT_CATALOG_PATH).sources)

    for track, target in TRACK_TARGETS.items():
        assert counts[track] >= target, f"{track.value}: {counts[track]}/{target}"
