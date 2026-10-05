from datetime import UTC, datetime

import httpx

from news_insight.collect.contracts import CollectContext
from news_insight.collect.registry import collector_for
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import check_network
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source

ROOT = "https://data.epo.org/publication-server/rest/v1.2/publication-dates"


def epo_fetcher():
    def handler(request):
        if request.url.path.endswith("document.xml"):
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                content=(
                    b"<ep-patent-document><B540><B541>en</B541>"
                    b"<B542>Precision technology</B542></B540></ep-patent-document>"
                ),
            )
        if request.url.path.endswith("publication-dates"):
            content = (
                b'<a href="/publication-server/rest/v1.2/publication-dates/20260930/patents">'
                b"2026/09/30</a>"
                b'<a href="/publication-server/rest/v1.2/publication-dates/20261007/patents">'
                b"2026/10/07</a>"
            )
        else:
            assert "/20260930/" in request.url.path
            content = b"".join(
                f'<a href="/publication-server/rest/v1.2/patents/EP{n}NWA1">EP{n}NWA1</a>'.encode()
                for n in range(1, 5)
            )
        return httpx.Response(200, headers={"content-type": "text/html"}, content=content)

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda h, p: ["93.184.216.34"],
        verify_peer=False,
    )


def test_weekly_bibliographic_pilot_ignores_future_publication_dates():
    context = CollectContext(
        endpoint_url=ROOT,
        now=datetime(2026, 10, 5, tzinfo=UTC),
        config={"mode": "epo_publications", "item_limit": 1},
    )
    result = collector_for(AccessMethod.RESEARCH_API, epo_fetcher()).collect(context)
    assert len(result.items) == 4
    assert result.items[0].stable_id == "epo:EP1NWA1"
    assert result.items[0].published_at == datetime(2026, 9, 30, tzinfo=UTC)
    assert result.items[0].title == "Precision technology"


def test_documented_epo_api_html_representation_passes_network_check():
    source = build_source(
        access_method=AccessMethod.RESEARCH_API,
        endpoint_url=ROOT,
        config={"mode": "epo_publications"},
    )
    assert check_network(source, epo_fetcher()).passed


def test_patent_pilot_has_an_explicit_cap_independent_of_news_item_limit():
    context = CollectContext(
        endpoint_url=ROOT,
        now=datetime(2026, 10, 5, tzinfo=UTC),
        config={"mode": "epo_publications", "max_documents": 3},
    )
    result = collector_for(AccessMethod.RESEARCH_API, epo_fetcher()).collect(context)
    assert len(result.items) == 3
