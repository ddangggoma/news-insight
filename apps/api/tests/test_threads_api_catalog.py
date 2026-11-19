"""scripts/threads-api-catalog.py: crawler entries become API entries the catalog accepts."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from news_insight.collect.presets import effective_config
from news_insight.sources.catalog import Catalog

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "threads-api-catalog.py"
CRAWLER = {
    "track": "community",
    "category": "open_social",
    "access_method": "crawler",
    "official_domain": "threads.com",
    "operator": "Meta Platforms",
    "region": "global_en",
    "language": "en",
    "poll_class": "community",
    "terms_url": "https://help.instagram.com/769983657850450",
    "storage_right": "excerpt_allowed",
}
CRAWLER_CONFIG = {
    "mode": "threads",
    "manual_review": True,
    "crawl_permitted": True,
    "robots_checked": True,
    "robots_note": "user decision",
    "min_interval_minutes": 60,
    "max_age_days": 14,
    "quiet_days": 21,
    "themes": ["robotics"],
}


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("threads_api_catalog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog_text() -> str:
    sources = [
        {
            "key": "rss-example",
            "name": "Example feed",
            **CRAWLER,
            "access_method": "feed",
            "endpoint_url": "https://www.example.com/feed",
            "official_domain": "example.com",
            "dx_relevance": "an unrelated source that must not change",
        },
        {
            "key": "threads-search-humanoid-robot",
            "name": "Threads search: humanoid robot",
            **CRAWLER,
            "endpoint_url": "https://www.threads.com/search?q=humanoid%20robot&serp_type=default",
            "dx_relevance": "Threads에서 'humanoid robot' 인기 글의 화제·반응 신호 (로봇)",
            "config": CRAWLER_CONFIG,
        },
        {
            "key": "threads-profile-example",
            "name": "Threads @example.news (Example)",
            **CRAWLER,
            "endpoint_url": "https://www.threads.com/@example.news",
            "dx_relevance": "Threads IT 매체 @example.news의 새 글과 반응",
            "config": {**CRAWLER_CONFIG, "min_interval_minutes": 180, "themes": ["media"]},
        },
    ]
    body = "".join(
        "  " + line if line.strip() else line
        for line in yaml.safe_dump(sources, sort_keys=False, allow_unicode=True).splitlines(True)
    )
    return "version: 1\nsources:\n" + body


def test_search_entries_become_keyword_search_sources(script: ModuleType) -> None:
    text, keys = script.with_api_entries(catalog_text(), "search", "TOP")

    assert keys == ["threads-api-search-humanoid-robot"]
    catalog = Catalog.model_validate(yaml.safe_load(text))
    entry = next(e for e in catalog.sources if e.key == keys[0])
    assert entry.access_method.value == "json_api"
    assert entry.endpoint_url == (
        "https://graph.threads.net/v1.0/keyword_search?q=humanoid%20robot&search_type=TOP"
    )
    assert entry.config["auth"] == {"secret": "THREADS_TOKEN"}
    assert entry.config["min_interval_minutes"] == 60
    assert entry.config["themes"] == ["robotics"]
    assert not {"mode", "crawl_permitted", "robots_note"} & set(entry.config)
    assert "반응" not in entry.dx_relevance
    assert effective_config(entry.config)["list_path"] == "data"
    assert text.startswith(catalog_text())  # other entries keep their text


def test_profiles_convert_only_when_asked_and_runs_are_idempotent(script: ModuleType) -> None:
    once, keys = script.with_api_entries(catalog_text(), "all", "RECENT")
    twice, again = script.with_api_entries(once, "all", "RECENT")

    assert sorted(keys) == ["threads-api-profile-example", "threads-api-search-humanoid-robot"]
    assert (twice, again) == (once, [])
    profile = next(
        e for e in yaml.safe_load(once)["sources"] if e["key"] == "threads-api-profile-example"
    )
    assert profile["endpoint_url"] == (
        "https://graph.threads.net/v1.0/profile_posts?username=example.news"
    )
    assert profile["config"]["preset"] == "threads_profile_posts"


def test_drop_crawler_removes_only_converted_entries(script: ModuleType) -> None:
    converted, _ = script.with_api_entries(catalog_text(), "search", "TOP")

    text, dropped = script.without_crawler_entries(converted, "all")

    assert dropped == ["threads-search-humanoid-robot"]  # the profile has no API twin yet
    keys = [e.key for e in Catalog.model_validate(yaml.safe_load(text)).sources]
    assert keys == ["rss-example", "threads-profile-example", "threads-api-search-humanoid-robot"]
