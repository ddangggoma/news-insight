"""Field mappings for JSON-shaped APIs, verified against live responses (2026-10-03).

A catalog entry picks one with `config.preset`; its own keys override the preset, and
`fields` / `metrics` merge key by key.
"""

from collections.abc import Mapping
from typing import Any

# Media fields both Threads endpoints return for other users' public posts (2026-11-19 docs);
# asking for an undocumented field fails the whole request.
THREADS_FIELDS = (
    "id,shortcode,text,media_type,permalink,timestamp,username,is_reply,link_attachment_url"
)
THREADS_POSTS: dict[str, Any] = {
    "list_path": "data",
    "fields": {
        "id": ["shortcode", "id"],
        "url": [],
        "title": "text",
        "summary": "text",
        "published_at": "timestamp",
        "author": "username",
        "link": "link_attachment_url",
    },
    "url_template": "https://www.threads.com/@{username}/post/{shortcode}",
    "title_first_line": True,
    "title_limit": 200,
    "summary_limit": 500,
    # replies and bare reposts are not posts of their own (the crawler skips them too)
    "skip_when": {"is_reply": True, "media_type": "REPOST_FACADE"},
    "max_age_days": 14,
}

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
            "summary_index": "abstract_inverted_index",
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
            "summary": "abstract",
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
            "summary": "abstractText",
            "published_at": "firstPublicationDate",
            "author": "authorString",
        },
        # abstracts come only with resultType=core (2026-10-11: 22 of 25 results had one)
        "query_overrides": {"resultType": "core"},
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
        # view counts come from a second call, videos?part=statistics
        "video_stats": True,
    },
    # Official Threads API (graph.threads.net/v1.0, token as a Bearer header from
    # config.auth.secret THREADS_TOKEN, so it never appears in a URL or a stored error).
    # Items match the logged-out crawler's (collect/threads.py): id = shortcode, the same
    # www.threads.com permalink, the first line as title, 500 characters of text. The API
    # documents no like/reply/repost/quote counts on other users' posts (insights cover only
    # the token owner's own media), so these sources carry no metrics.
    # Keyword search: developers.facebook.com/docs/threads/keyword-search
    "threads_keyword_search": {**THREADS_POSTS, "query_overrides": {"fields": THREADS_FIELDS}},
    # A public profile's posts (threads_profile_discovery):
    # developers.facebook.com/docs/threads/threads-profiles
    "threads_profile_posts": {**THREADS_POSTS, "query_overrides": {"fields": THREADS_FIELDS}},
    # Hugging Face daily papers (curated, with upvotes); the sitemap source only saw Spaces.
    "hf_daily_papers": {
        "list_path": "",
        "fields": {
            "id": "paper.id",
            "url": [],
            "title": "title",
            "summary": "summary",
            "published_at": "publishedAt",
        },
        "url_template": "https://huggingface.co/papers/{paper.id}",
        "metrics": {"upvotes": "paper.upvotes", "comments": "numComments"},
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
