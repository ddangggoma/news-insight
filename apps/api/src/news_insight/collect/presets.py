"""Field mappings for JSON-shaped APIs, verified against live responses (2026-10-03).

A catalog entry picks one with `config.preset`; its own keys override the preset, and
`fields` / `metrics` merge key by key.
"""

from collections.abc import Mapping
from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "github_search": {
        "list_path": "items",
        "fields": {
            "id": "full_name",
            "url": "html_url",
            "title": "full_name",
            "summary": "description",
            "published_at": "pushed_at",
            "author": "owner.login",
        },
        "metrics": {
            "stars": "stargazers_count",
            "forks": "forks_count",
            "open_issues": "open_issues_count",
        },
    },
    "github_releases": {
        "list_path": "",
        "fields": {
            "id": "id",
            "url": "html_url",
            "title": ["name", "tag_name"],
            "summary": "body",
            "published_at": "published_at",
            "author": "author.login",
        },
    },
    "github_advisories": {
        "list_path": "",
        "fields": {
            "id": "ghsa_id",
            "url": "html_url",
            "title": "summary",
            "summary": "description",
            "published_at": "published_at",
            "author": "cve_id",
        },
    },
    "bluesky_author_feed": {
        "list_path": "feed",
        "fields": {
            "id": "post.uri",
            "url": [],
            "title": ["post.record.text", "post.embed.external.title"],
            "summary": ["post.record.text", "post.embed.external.description"],
            "published_at": "post.record.createdAt",
            "author": "post.author.handle",
            "link": "post.embed.external.uri",
        },
        "url_template": "https://bsky.app/profile/{post.author.handle}/post/{post.uri|last}",
        "title_limit": 120,
        "metrics": {
            "likes": "post.likeCount",
            "reposts": "post.repostCount",
            "replies": "post.replyCount",
        },
    },
    "mastodon_timeline": {
        "list_path": "",
        "fields": {
            "id": "uri",
            "url": ["url", "uri"],
            "title": "content",
            "summary": "content",
            "published_at": "created_at",
            "author": "account.acct",
            "link": "card.url",
        },
        "title_limit": 120,
        "metrics": {
            "favourites": "favourites_count",
            "reblogs": "reblogs_count",
            "replies": "replies_count",
        },
    },
    "stackexchange_questions": {
        "list_path": "items",
        "fields": {
            "id": "question_id",
            "url": "link",
            "title": "title",
            "published_at": "creation_date",
            "author": "owner.display_name",
        },
        "metrics": {"score": "score", "answers": "answer_count", "views": "view_count"},
    },
    "hn_algolia": {
        "list_path": "hits",
        "fields": {
            "id": "objectID",
            "url": "url",
            "title": "title",
            "published_at": "created_at",
            "author": "author",
        },
        "url_template": "https://news.ycombinator.com/item?id={objectID}",
        "metrics": {"points": "points", "comments": "num_comments"},
    },
    "devto_articles": {
        "list_path": "",
        "fields": {
            "id": "id",
            "url": "url",
            "title": "title",
            "summary": "description",
            "published_at": "published_at",
            "author": "user.username",
        },
        "metrics": {"reactions": "positive_reactions_count", "comments": "comments_count"},
    },
    "openalex_works": {
        "list_path": "results",
        "fields": {
            "id": "id",
            "url": ["primary_location.landing_page_url", "doi", "id"],
            "title": "display_name",
            "published_at": "publication_date",
            "author": "authorships.0.author.display_name",
        },
        "metrics": {"citations": "cited_by_count"},
    },
    "crossref_works": {
        "list_path": "message.items",
        "fields": {
            "id": "DOI",
            "url": "URL",
            "title": "title.0",
            "published_at": "created.date-time",
            "author": "author.0.family",
        },
        "metrics": {"citations": "is-referenced-by-count"},
    },
    "europepmc_search": {
        "list_path": "resultList.result",
        "fields": {
            "id": "id",
            "url": [],
            "title": "title",
            "published_at": "firstPublicationDate",
            "author": "authorString",
        },
        "url_template": "https://europepmc.org/article/{source}/{id}",
        "metrics": {"citations": "citedByCount"},
    },
    # Official keyword search APIs (developers.naver.com; X-Naver-Client-Id/Secret headers).
    "naver_news_search": {
        "list_path": "items",
        "fields": {
            "id": ["originallink", "link"],
            "url": ["originallink", "link"],
            "title": "title",
            "summary": "description",
            "published_at": "pubDate",
        },
    },
    "naver_blog_search": {
        "list_path": "items",
        "fields": {
            "id": "link",
            "url": "link",
            "title": "title",
            "summary": "description",
            "published_at": "postdate",
            "author": "bloggername",
        },
    },
    # Hugging Face Hub public API (models / datasets / spaces listing), no token needed.
    "huggingface_hub": {
        "list_path": "",
        "fields": {
            "id": "id",
            "url": [],
            "title": "id",
            "summary": "pipeline_tag",
            "published_at": ["lastModified", "createdAt"],
            "author": "author",
        },
        "url_template": "https://huggingface.co/{id|path}",
        "metrics": {"likes": "likes", "downloads": "downloads", "trending": "trendingScore"},
    },
    # YouTube Data API v3 playlistItems (channel uploads playlist UU...), X-Goog-Api-Key header.
    "youtube_playlist": {
        "list_path": "items",
        "fields": {
            "id": "snippet.resourceId.videoId",
            "url": [],
            "title": "snippet.title",
            "summary": "snippet.description",
            "published_at": "snippet.publishedAt",
            "author": "snippet.videoOwnerChannelTitle",
        },
        "url_template": "https://www.youtube.com/watch?v={snippet.resourceId.videoId}",
    },
}


def effective_config(config: Mapping[str, Any]) -> dict[str, Any]:
    name = config.get("preset")
    if not name:
        return dict(config)
    if name not in PRESETS:
        raise ValueError(f"unknown preset '{name}'")
    base = PRESETS[str(name)]
    merged: dict[str, Any] = {
        **base,
        **{key: value for key, value in config.items() if key != "preset"},
    }
    merged["fields"] = {**base.get("fields", {}), **dict(config.get("fields") or {})}
    merged["metrics"] = {**base.get("metrics", {}), **dict(config.get("metrics") or {})}
    return merged
