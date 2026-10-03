import json
from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.presets import PRESETS, effective_config
from tests.helpers import serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

CASES: list[tuple[str, dict[str, Any], tuple[str, str, str, datetime, dict[str, int]]]] = [
    (
        "github_search",
        {
            "full_name": "alibaba/MNN",
            "html_url": "https://github.com/alibaba/MNN",
            "description": "MNN engine",
            "pushed_at": "2026-10-01T09:00:00Z",
            "owner": {"login": "alibaba"},
            "stargazers_count": 16168,
            "forks_count": 2463,
            "open_issues_count": 12,
        },
        (
            "alibaba/MNN",
            "https://github.com/alibaba/MNN",
            "alibaba/MNN",
            OCT_1_0900,
            {"stars": 16168, "forks": 2463, "open_issues": 12},
        ),
    ),
    (
        "github_releases",
        {
            "id": 7,
            "html_url": "https://github.com/o/r/releases/tag/v1.0",
            "name": "",
            "tag_name": "v1.0",
            "published_at": "2026-10-01T09:00:00Z",
        },
        ("7", "https://github.com/o/r/releases/tag/v1.0", "v1.0", OCT_1_0900, {}),
    ),
    (
        "github_advisories",
        {
            "ghsa_id": "GHSA-h46j-26q3-rggf",
            "html_url": "https://github.com/advisories/GHSA-h46j-26q3-rggf",
            "summary": "Headroom vulnerable to CSWSH",
            "published_at": "2026-10-01T09:00:00Z",
        },
        (
            "GHSA-h46j-26q3-rggf",
            "https://github.com/advisories/GHSA-h46j-26q3-rggf",
            "Headroom vulnerable to CSWSH",
            OCT_1_0900,
            {},
        ),
    ),
    (
        "bluesky_author_feed",
        {
            "post": {
                "uri": "at://did:plc:ifn/app.bsky.feed.post/3mwq",
                "author": {"handle": "aster.id"},
                "record": {
                    "text": "The modern research ecosystem",
                    "createdAt": "2026-10-01T09:00:00Z",
                },
                "likeCount": 717,
                "repostCount": 143,
                "replyCount": 16,
            }
        },
        (
            "at://did:plc:ifn/app.bsky.feed.post/3mwq",
            "https://bsky.app/profile/aster.id/post/3mwq",
            "The modern research ecosystem",
            OCT_1_0900,
            {"likes": 717, "reposts": 143, "replies": 16},
        ),
    ),
    (
        "mastodon_timeline",
        {
            "id": "117",
            "uri": "https://mastodon.social/users/m/statuses/117",
            "url": "https://mastodon.social/@m/117",
            "content": "<p>Ghost Trail feature</p>",
            "created_at": "2026-10-01T09:00:00Z",
            "account": {"acct": "m"},
            "favourites_count": 3,
            "reblogs_count": 1,
            "replies_count": 0,
        },
        (
            "https://mastodon.social/users/m/statuses/117",
            "https://mastodon.social/@m/117",
            "Ghost Trail feature",
            OCT_1_0900,
            {"favourites": 3, "reblogs": 1, "replies": 0},
        ),
    ),
    (
        "stackexchange_questions",
        {
            "question_id": 80007455,
            "link": "https://stackoverflow.com/questions/80007455/aab-size",
            "title": "Why is my AAB file 85 MB?",
            "creation_date": 1790845200,
            "owner": {"display_name": "Dawood"},
            "score": 1,
            "answer_count": 1,
            "view_count": 71,
        },
        (
            "80007455",
            "https://stackoverflow.com/questions/80007455/aab-size",
            "Why is my AAB file 85 MB?",
            OCT_1_0900,
            {"score": 1, "answers": 1, "views": 71},
        ),
    ),
    (
        "hn_algolia",
        {
            "objectID": "49941447",
            "url": None,
            "title": "Ask HN: on-device AI?",
            "created_at": "2026-10-01T09:00:00Z",
            "author": "p",
            "points": 63,
            "num_comments": 29,
        },
        (
            "49941447",
            "https://news.ycombinator.com/item?id=49941447",
            "Ask HN: on-device AI?",
            OCT_1_0900,
            {"points": 63, "comments": 29},
        ),
    ),
    (
        "devto_articles",
        {
            "id": 4786527,
            "url": "https://dev.to/dj29/hacktoberfest",
            "title": "Hacktoberfest",
            "description": "d",
            "published_at": "2026-10-01T09:00:00Z",
            "user": {"username": "dj29"},
            "positive_reactions_count": 54,
            "comments_count": 15,
        },
        (
            "4786527",
            "https://dev.to/dj29/hacktoberfest",
            "Hacktoberfest",
            OCT_1_0900,
            {"reactions": 54, "comments": 15},
        ),
    ),
    (
        "openalex_works",
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1/x",
            "display_name": "On-device inference",
            "publication_date": "2026-10-01",
            "primary_location": {"landing_page_url": "https://zenodo.org/record/1"},
            "authorships": [{"author": {"display_name": "Azuaje"}}],
            "cited_by_count": 4,
        },
        (
            "https://openalex.org/W1",
            "https://zenodo.org/record/1",
            "On-device inference",
            datetime(2026, 10, 1, tzinfo=UTC),
            {"citations": 4},
        ),
    ),
    (
        "crossref_works",
        {
            "DOI": "10.1111/sms.70378",
            "URL": "https://doi.org/10.1111/sms.70378",
            "title": ["Wearable sensing"],
            "created": {"date-time": "2026-10-01T09:00:00Z"},
            "author": [{"family": "Sprouse"}],
            "is-referenced-by-count": 0,
        },
        (
            "10.1111/sms.70378",
            "https://doi.org/10.1111/sms.70378",
            "Wearable sensing",
            OCT_1_0900,
            {"citations": 0},
        ),
    ),
    (
        "europepmc_search",
        {
            "id": "42741683",
            "source": "MED",
            "title": "AI-guided nanozyme",
            "firstPublicationDate": "2026-10-01",
            "authorString": "Yang D",
            "citedByCount": 2,
        },
        (
            "42741683",
            "https://europepmc.org/article/MED/42741683",
            "AI-guided nanozyme",
            datetime(2026, 10, 1, tzinfo=UTC),
            {"citations": 2},
        ),
    ),
]


def wrap(list_path: str, records: list[dict[str, Any]]) -> Any:
    payload: Any = records
    for part in reversed([part for part in list_path.split(".") if part]):
        payload = {part: payload}
    return payload


@pytest.mark.parametrize(("preset", "record", "expected"), CASES, ids=[case[0] for case in CASES])
def test_presets_map_real_response_shapes(
    preset: str,
    record: dict[str, Any],
    expected: tuple[str, str, str, datetime, dict[str, int]],
) -> None:
    config = effective_config({"preset": preset})
    body = json.dumps(wrap(str(config.get("list_path", "")), [record])).encode()
    context = CollectContext(endpoint_url="https://api.example.com/x", config=config, now=NOW)

    [item] = JsonApiCollector(serving(body, content_type="application/json")).collect(context).items

    assert (item.stable_id, item.url, item.title, item.published_at, item.metrics) == expected


def test_every_preset_is_covered() -> None:
    assert {case[0] for case in CASES} == set(PRESETS)


def test_source_config_overrides_and_merges_the_preset() -> None:
    config = effective_config(
        {"preset": "github_search", "item_limit": 10, "fields": {"summary": "topics.0"}}
    )

    assert config["item_limit"] == 10
    assert config["fields"]["summary"] == "topics.0"
    assert config["fields"]["url"] == "html_url"
    assert "preset" not in config


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="unknown preset 'nope'"):
        effective_config({"preset": "nope"})
