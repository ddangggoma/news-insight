"""Patent collector (plan 16 #5): EPO OPS published-data search."""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from news_insight.collect import epo_ops
from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.json_api import JsonApiCollector
from tests.helpers import mock_fetcher, serving

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
CATL_NAME = "CONTEMPORARY AMPEREX TECHNOLOGY CO LTD"

OPS_ANSWER: dict[str, Any] = {
    "ops:world-patent-data": {
        "ops:biblio-search": {
            "@total-result-count": "2",
            "ops:search-result": {
                "exchange-documents": [
                    {
                        "exchange-document": {
                            "@country": "CN",
                            "@doc-number": "118765432",
                            "@kind": "A",
                            "bibliographic-data": {
                                "publication-reference": {
                                    "document-id": [
                                        {"@document-id-type": "docdb", "date": {"$": "20261007"}}
                                    ]
                                },
                                "invention-title": [
                                    {"@lang": "zh", "$": "固态电池电解质"},
                                    {"@lang": "en", "$": "Solid-state battery electrolyte"},
                                ],
                                "parties": {
                                    "applicants": {
                                        "applicant": [
                                            {
                                                "@data-format": "epodoc",
                                                "applicant-name": {"name": {"$": "CATL [CN]"}},
                                            },
                                            {
                                                "@data-format": "original",
                                                "applicant-name": {"name": {"$": CATL_NAME}},
                                            },
                                        ]
                                    }
                                },
                            },
                            "abstract": {
                                "@lang": "en",
                                "p": {"$": "A sulfide electrolyte  layer."},
                            },
                        }
                    },
                    {  # a single document arrives as a dict, a title as a dict too
                        "exchange-document": {
                            "@country": "EP",
                            "@doc-number": "4500001",
                            "@kind": "A1",
                            "bibliographic-data": {
                                "invention-title": {"@lang": "en", "$": "Foldable OLED hinge"}
                            },
                        }
                    },
                    {"exchange-document": {"@country": "EP", "bibliographic-data": {}}},
                ]
            },
        }
    }
}


def test_ops_records_become_items() -> None:
    items = epo_ops.to_items(OPS_ANSWER)
    assert [i.stable_id for i in items] == ["CN118765432A", "EP4500001A1"]
    first = items[0]
    assert first.title == "Solid-state battery electrolyte"
    assert first.published_at == datetime(2026, 10, 7, tzinfo=UTC)
    assert first.author == "CATL; CONTEMPORARY AMPEREX TECHNOLOGY CO LTD"
    assert first.summary == "A sulfide electrolyte layer."
    assert first.url.endswith("pn%3DCN118765432A")
    assert items[1].published_at is None and items[1].author is None
    assert items[1].stable_id == "EP4500001A1"


def test_ops_search_url_expands_dates_as_yyyymmdd() -> None:
    url = epo_ops.search_url({"cql": "pn=CN and cpc=H01M and pd>={today-30d}", "range": 500}, NOW)
    assert "pd%3E%3D20260910" in url and url.endswith("&Range=1-100")
    with pytest.raises(CollectorError):
        epo_ops.search_url({}, NOW)


def test_ops_needs_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_SECRET_EPO_OPS_KEY", raising=False)
    context = CollectContext(
        endpoint_url=epo_ops.SEARCH_URL, config={"mode": "epo_ops", "cql": "pn=EP"}, now=NOW
    )
    with pytest.raises(CollectorError) as error:
        JsonApiCollector(serving(b"{}", content_type="application/json")).collect(context)
    assert error.value.code == "config_error" and "EPO_OPS_KEY" in str(error.value)


def test_ops_takes_a_token_once_and_searches_with_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_SECRET_EPO_OPS_KEY", "consumer")
    monkeypatch.setenv("SOURCE_SECRET_EPO_OPS_SECRET", "s3cret")
    epo_ops._tokens.clear()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/auth/accesstoken"):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=json.dumps({"access_token": "tok", "expires_in": "1199"}).encode(),
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(OPS_ANSWER).encode(),
        )

    fetcher = mock_fetcher(handler)
    context = CollectContext(
        endpoint_url=epo_ops.SEARCH_URL,
        config={"mode": "epo_ops", "cql": "pn=CN and cpc=H01M"},
        now=NOW,
    )
    for _ in range(2):
        result = JsonApiCollector(fetcher).collect(context)
        assert len(result.items) == 2
    token_calls = [r for r in seen if r.url.path.endswith("/auth/accesstoken")]
    assert len(token_calls) == 1 and token_calls[0].method == "POST"
    assert token_calls[0].headers["authorization"].startswith("Basic ")
    assert seen[-1].headers["authorization"] == "Bearer tok"
    epo_ops._tokens.clear()
