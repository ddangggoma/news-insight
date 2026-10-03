from news_insight.sources.checks import check_identity, check_policy, probe_url
from news_insight.sources.enums import AccessMethod, Region, StorageRight, Track
from tests.factories import build_source


def test_identity_passes_for_subdomain_of_official_domain() -> None:
    result = check_identity(build_source(endpoint_url="https://feeds.example.com/rss"))

    assert result.passed, result.reasons
    assert result.metrics["endpoint_host"] == "feeds.example.com"


def test_identity_rejects_foreign_host() -> None:
    result = check_identity(build_source(endpoint_url="https://evil-example.com/rss"))

    assert not result.passed
    assert "endpoint host 'evil-example.com' is not under official domain 'example.com'" in (
        result.reasons
    )


def test_identity_accepts_explicitly_allowed_host() -> None:
    source = build_source(
        endpoint_url="https://feeds.feedburner.com/example",
        config={"allowed_hosts": ["feeds.feedburner.com"]},
    )

    assert check_identity(source).passed


def test_identity_checks_probe_url_host_too() -> None:
    source = build_source(config={"probe_url": "https://other.org/probe"})

    result = check_identity(source)

    assert "probe host 'other.org' is not under official domain 'example.com'" in result.reasons


def test_identity_requires_operator_and_dx_rationale() -> None:
    result = check_identity(build_source(operator=" ", dx_relevance="short"))

    assert "operator is missing" in result.reasons
    assert "dx_relevance rationale is missing or too short" in result.reasons


def test_identity_flags_language_region_mismatch() -> None:
    result = check_identity(build_source(region=Region.KR, language="ja"))

    assert "language 'ja' does not match region 'kr'" in result.reasons


def test_identity_allows_any_language_for_eu_other() -> None:
    assert check_identity(build_source(region=Region.EU_OTHER, language="de")).passed


def test_policy_passes_with_terms_and_storage_right() -> None:
    assert check_policy(build_source()).passed


def test_policy_requires_https_terms_and_storage_right() -> None:
    missing = check_policy(build_source(terms_url=None, storage_right=None))
    insecure = check_policy(build_source(terms_url="http://www.example.com/terms"))

    assert missing.reasons == ["terms_url is missing", "storage_right is not declared"]
    assert insecure.reasons == ["terms_url must use https"]


def test_policy_requires_reviewed_declarative_crawler() -> None:
    result = check_policy(build_source(access_method=AccessMethod.CRAWLER, config={}))

    assert result.reasons == [
        "crawler requires config.crawl_permitted=true after terms review",
        "crawler requires config.robots_checked=true",
        "crawler requires declarative config.selectors",
    ]


def test_policy_blocks_research_fulltext_without_open_access() -> None:
    source = build_source(track=Track.RESEARCH_IP, storage_right=StorageRight.FULLTEXT_PERMITTED)

    result = check_policy(source)

    assert not result.passed
    assert "paywall bypass is forbidden" in result.reasons[0]


def test_policy_allows_research_fulltext_with_open_access() -> None:
    source = build_source(
        track=Track.RESEARCH_IP,
        storage_right=StorageRight.FULLTEXT_TTL,
        config={"open_access": True},
    )

    assert check_policy(source).passed


def test_probe_url_prefers_config_override() -> None:
    assert probe_url(build_source()) == "https://www.example.com/feed.xml"
    assert probe_url(build_source(config={"probe_url": "https://example.com/p"})) == (
        "https://example.com/p"
    )
