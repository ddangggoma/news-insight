"""research.enrich: which papers are asked, what is stored, and when a run stops."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import ItemDedup
from news_insight.research import service
from news_insight.research.models import EnrichStatus, ResearchMeta
from news_insight.research.service import due_items, enrich, pick_lookup, scrub
from news_insight.scheduling import providers
from news_insight.scheduling.providers import OPENALEX_WORKS, Provider, ProviderGate
from news_insight.sources.enums import Track
from tests.documents import SEEN, document, source
from tests.helpers import mock_fetcher

pytestmark = pytest.mark.db

NOW = SEEN + timedelta(days=3, hours=2)  # past the OpenAlex index lag
FIXTURES = Path(__file__).parent / "fixtures"
ATTENTION = (FIXTURES / "openalex_attention.json").read_bytes()
ALPHAFOLD = (FIXTURES / "openalex_alphafold.json").read_bytes()


def answering(
    bodies: dict[str, tuple[int, bytes]], seen: list[httpx.Request] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        for needle, (status, body) in bodies.items():
            if needle in str(request.url):
                kind = "application/json" if status == 200 else "text/html"
                return httpx.Response(status, headers={"content-type": kind}, content=body)
        return httpx.Response(404, headers={"content-type": "text/html"}, content=b"<h1>404</h1>")

    return handler


def meta(session: Session, item_id: int) -> ResearchMeta:
    row = session.get(ResearchMeta, item_id)
    assert row is not None
    session.refresh(row)
    return row


def test_enrich_stores_openalex_metadata_and_links_companies(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(
        db_session,
        src,
        "attention",
        refs=(("arxiv", "1706.03762"),),
        url="https://arxiv.org/abs/1706.03762v7",
    )
    seen: list[httpx.Request] = []
    fetcher = mock_fetcher(answering({"1706.03762": (200, ATTENTION)}, seen))

    result = enrich(db_session, fetcher, now=NOW)

    assert (result.attempted, result.ok, result.stopped) == (1, 1, None)
    assert "/works/doi:10.48550/arxiv.1706.03762?select=" in str(seen[0].url)
    row = meta(db_session, paper.id)
    assert row.status == EnrichStatus.OK and row.enriched_at == NOW
    assert row.doi == "10.48550/arxiv.1706.03762" and row.openalex_id == "W2626778328"
    assert (
        row.venue == "arXiv (Cornell University)" and row.oa_subfield == "Artificial Intelligence"
    )
    assert row.has_company and row.company_keys == ["google"]
    assert row.countries == ["CA", "US"]
    assert row.institutions[0] == {
        "name": "Google (United States)",
        "type": "company",
        "country": "US",
        "ror": "https://ror.org/00njsd438",
        "company_key": "google",
    }
    assert row.institutions[1]["company_key"] is None  # a university stays an organisation
    assert row.cited_by and row.cited_by > 100_000


def test_only_company_institutions_are_linked(db_session: Session) -> None:
    src = source(db_session, "openalex-nature")
    paper = document(
        db_session,
        src,
        "alphafold",
        refs=(("doi", "10.1038/s41586-021-03819-2"),),
        url="https://doi.org/10.1038/s41586-021-03819-2",
    )
    fetcher = mock_fetcher(answering({"s41586-021-03819-2": (200, ALPHAFOLD)}))

    enrich(db_session, fetcher, now=NOW)

    row = meta(db_session, paper.id)
    assert row.company_keys == ["googledeepmind"] and row.fwci == pytest.approx(2020.1166)
    by_name = {i["name"]: i["company_key"] for i in row.institutions}
    assert by_name == {
        "Google DeepMind (United Kingdom)": "googledeepmind",
        "Seoul National University": None,
    }


def test_not_found_is_asked_again_after_seven_days(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(
        db_session,
        src,
        "fresh",
        refs=(("arxiv", "2611.00001"),),
        url="https://arxiv.org/abs/2611.00001",
    )

    result = enrich(db_session, mock_fetcher(answering({})), now=NOW)

    assert (result.not_found, result.ok) == (1, 0)
    row = meta(db_session, paper.id)
    assert row.status == EnrichStatus.NOT_FOUND and row.openalex_id is None
    assert row.doi == "10.48550/arxiv.2611.00001"
    assert paper.id not in ids(db_session, NOW + timedelta(days=6))
    assert paper.id in ids(db_session, NOW + timedelta(days=7, minutes=1))


def test_not_found_stops_being_asked_once_the_paper_is_old(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "old", refs=(("arxiv", "2611.00002"),))
    enrich(db_session, mock_fetcher(answering({})), now=NOW)

    assert paper.id not in ids(db_session, SEEN + timedelta(days=91))


def test_a_found_paper_is_refreshed_after_thirty_days(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(
        db_session,
        src,
        "attention",
        refs=(("arxiv", "1706.03762"),),
        url="https://arxiv.org/abs/1706.03762v7",
    )
    enrich(db_session, mock_fetcher(answering({"1706.03762": (200, ATTENTION)})), now=NOW)

    assert paper.id not in ids(db_session, NOW + timedelta(days=29))
    assert paper.id in ids(db_session, NOW + timedelta(days=30, minutes=1))


def test_errors_are_kept_retried_next_day_and_stop_a_failing_run(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    papers = [
        document(db_session, src, f"p{n}", refs=(("arxiv", f"2611.0001{n}"),)) for n in range(7)
    ]
    fetcher = mock_fetcher(lambda request: httpx.Response(503, content=b"busy"))

    result = enrich(db_session, fetcher, now=NOW)

    assert (result.attempted, result.errors, result.stopped) == (5, 5, "errors")
    first = papers[-1]  # same date: the higher id first
    row = meta(db_session, first.id)
    assert row.status == EnrichStatus.ERROR and row.error and "server_error" in row.error
    assert db_session.get(ResearchMeta, papers[0].id) is None  # not reached: still new
    assert first.id not in ids(db_session, NOW + timedelta(hours=23))
    assert first.id in ids(db_session, NOW + timedelta(days=1, minutes=1))


def test_unreadable_json_is_an_error(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "broken", refs=(("arxiv", "2611.00003"),))

    enrich(db_session, mock_fetcher(answering({"2611.00003": (200, b"{not json")})), now=NOW)

    assert meta(db_session, paper.id).status == EnrichStatus.ERROR


def test_new_papers_first_newest_first_within_the_limit(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    older = document(
        db_session, src, "older", refs=(("arxiv", "2611.00004"),), published=SEEN - timedelta(1)
    )
    newer = document(db_session, src, "newer", refs=(("arxiv", "2611.00005"),))
    retry = document(
        db_session, src, "retry", refs=(("arxiv", "2611.00006"),), published=SEEN + timedelta(1)
    )
    db_session.add(
        ResearchMeta(
            item_id=retry.id,
            doi="10.48550/arxiv.2611.00006",
            status=EnrichStatus.NOT_FOUND,
            enriched_at=NOW - timedelta(days=8),
        )
    )
    db_session.flush()

    assert ids(db_session, NOW) == [newer.id, older.id, retry.id]
    assert [lookup.item_id for lookup in due_items(db_session, now=NOW, limit=2)] == [
        newer.id,
        older.id,
    ]


def test_skips_repeats_canaries_patents_and_papers_without_ids(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    keep = document(db_session, src, "keep", refs=(("arxiv", "2611.00007"),))
    repeat = document(db_session, src, "repeat", refs=(("arxiv", "2611.00008"),))
    dedup = db_session.get(ItemDedup, repeat.id)
    assert dedup is not None
    dedup.duplicate_of = keep.id
    document(db_session, src, "canary", refs=(("arxiv", "2611.00009"),), canary=True)
    document(db_session, src, "github-only", refs=(("github", "a/b"),))
    news = source(db_session, "tech-news", category="independent_media", track=Track.NEWS)
    document(db_session, news, "news", refs=(("arxiv", "2611.00010"),))
    office = source(db_session, "epo", category="patent_office")
    document(db_session, office, "patent", refs=(("doi", "10.1/epo"),))
    db_session.flush()

    assert ids(db_session, NOW) == [keep.id]


def test_pick_lookup_prefers_the_items_own_identifier() -> None:
    refs = [("arxiv", "2507.07505"), ("arxiv", "2609.39358")]

    own = pick_lookup(1, "T", "s", "https://arxiv.org/abs/2609.39358v1", refs)
    assert own is not None and (own.doi, own.verify_title) == ("10.48550/arxiv.2609.39358", False)
    crossref = pick_lookup(
        1, "T", "10.4081/cc.2026.16043", "https://x.org", [("doi", "10.4081/cc.2026.16043")]
    )
    assert crossref is not None and not crossref.verify_title  # the stable id is the DOI
    cited = pick_lookup(1, "T", "s", "https://x.org", [("arxiv", "2507.07505"), ("doi", "10.1/x")])
    assert cited is not None and (cited.doi, cited.verify_title) == ("10.1/x", True)
    assert pick_lookup(1, "T", "s", "https://x.org", [("github", "a/b")]) is None


def test_pick_lookup_uses_the_openalex_id_of_openalex_items() -> None:
    lookup = pick_lookup(
        1, "T", "https://openalex.org/W3177828909", "https://doi.org/10.9/x", [("doi", "10.9/x")]
    )

    assert lookup is not None and (lookup.openalex_id, lookup.doi) == ("W3177828909", None)
    assert lookup.url.startswith("https://api.openalex.org/works/W3177828909?select=")


def test_openalex_items_are_looked_up_by_work_id_even_without_a_doi(db_session: Session) -> None:
    src = source(db_session, "openalex-search")
    paper = document(
        db_session,
        src,
        "alphafold",
        stable_id="https://openalex.org/W3177828909",
        url="https://www.nature.com/articles/s41586-021-03819-2",
    )
    seen: list[httpx.Request] = []

    enrich(
        db_session, mock_fetcher(answering({"/works/W3177828909": (200, ALPHAFOLD)}, seen)), now=NOW
    )

    assert seen[0].url.path == "/works/W3177828909"
    row = meta(db_session, paper.id)
    assert row.status == EnrichStatus.OK and row.doi == "10.1038/s41586-021-03819-2"
    assert row.openalex_id == "W3177828909"


def test_a_cited_doi_whose_title_differs_is_not_the_paper(db_session: Session) -> None:
    src = source(db_session, "europepmc")
    cites = document(
        db_session,
        src,
        "cites",
        title="Protein language models for enzyme design",
        refs=(("doi", "10.1038/s41586-021-03819-2"),),
    )
    same = document(
        db_session,
        src,
        "same",
        title="Highly accurate protein structure prediction with AlphaFold.",
        refs=(("doi", "10.1038/s41586-021-03819-2"),),
    )

    enrich(db_session, mock_fetcher(answering({"s41586-021-03819-2": (200, ALPHAFOLD)})), now=NOW)

    wrong = meta(db_session, cites.id)
    assert wrong.status == EnrichStatus.NOT_FOUND and wrong.company_keys == []
    assert wrong.error == "title_mismatch: W3177828909"
    assert wrong.doi is None  # the cited paper's DOI is not this item's
    assert meta(db_session, same.id).status == EnrichStatus.OK


def test_a_json_answer_that_is_not_an_object_is_that_papers_error(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    odd = document(db_session, src, "odd", refs=(("arxiv", "2611.00040"),))
    good = document(
        db_session,
        src,
        "attention",
        refs=(("arxiv", "1706.03762"),),
        url="https://arxiv.org/abs/1706.03762v7",
        published=SEEN - timedelta(1),
    )
    fetcher = mock_fetcher(
        answering({"2611.00040": (200, b"[1, 2]"), "1706.03762": (200, ATTENTION)})
    )

    result = enrich(db_session, fetcher, now=NOW)

    assert (result.errors, result.ok, result.stopped) == (1, 1, None)
    assert "parse_error" in (meta(db_session, odd.id).error or "")
    assert meta(db_session, good.id).status == EnrichStatus.OK


def test_stored_errors_carry_no_query_strings() -> None:
    error = "server_error: HTTP 503 from https://api.openalex.org/works/doi:10.1/x?select=id&mailto=ops@example.com"

    assert scrub(error) == "server_error: HTTP 503 from https://api.openalex.org/works/doi:10.1/x"


def test_server_error_text_is_stored_without_the_mailto(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "polite_url", lambda url: f"{url}&mailto=ops@example.com")
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "p", refs=(("arxiv", "2611.00041"),))

    enrich(db_session, mock_fetcher(lambda request: httpx.Response(500, content=b"x")), now=NOW)

    error = meta(db_session, paper.id).error or ""
    assert "server_error" in error and "mailto" not in error and "?" not in error


def test_commits_every_hundred_attempts_whatever_the_outcome(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "COMMIT_EVERY", 2)
    commits: list[int] = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1))
    src = source(db_session, "arxiv-cs")
    for n in range(5):
        document(db_session, src, f"miss{n}", refs=(("arxiv", f"2611.0005{n}"),))

    result = enrich(db_session, mock_fetcher(answering({})), now=NOW)

    assert (result.not_found, len(commits)) == (5, 2)


def test_backoff_stops_the_run_before_any_request(
    db_session: Session, redis_client: redis.Redis
) -> None:
    src = source(db_session, "arxiv-cs")
    document(db_session, src, "p", refs=(("arxiv", "2611.00011"),))
    gate = ProviderGate(redis_client)
    gate.back_off("api.openalex.org", 600)
    seen: list[httpx.Request] = []

    result = enrich(db_session, mock_fetcher(answering({}, seen)), now=NOW, gate=gate)

    assert (result.attempted, result.stopped, seen) == (0, "provider_backoff", [])
    assert db_session.scalars(select(ResearchMeta)).all() == []


def test_an_empty_bucket_stops_the_run(
    db_session: Session, redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        providers.BUCKETS, OPENALEX_WORKS, Provider(per_day=1, burst=1, validate_per_batch=0)
    )
    src = source(db_session, "arxiv-cs")
    for n in range(3):
        document(db_session, src, f"p{n}", refs=(("arxiv", f"2611.0002{n}"),))
    gate = ProviderGate(redis_client)

    result = enrich(db_session, mock_fetcher(answering({})), now=NOW, gate=gate)

    assert (result.attempted, result.stopped) == (1, "provider_budget")


def test_a_429_pauses_the_whole_host_and_leaves_the_paper_due(
    db_session: Session, redis_client: redis.Redis
) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "p", refs=(("arxiv", "2611.00030"),))
    gate = ProviderGate(redis_client)
    fetcher = mock_fetcher(
        lambda request: httpx.Response(429, headers={"retry-after": "120"}, content=b"slow down")
    )

    result = enrich(db_session, fetcher, now=NOW, gate=gate)

    assert result.stopped == "rate_limited"
    assert 0 < gate.backoff_seconds("api.openalex.org") <= 120
    assert db_session.get(ResearchMeta, paper.id) is None


def ids(session: Session, now: datetime) -> list[int]:
    return [lookup.item_id for lookup in due_items(session, now=now, limit=100)]


def test_fixture_is_a_real_single_work_answer() -> None:
    assert json.loads(ATTENTION)["id"] == "https://openalex.org/W2626778328"


def test_a_new_paper_waits_out_the_openalex_index_lag(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "brand new", refs=(("arxiv", "2611.09999"),), published=SEEN)
    assert paper.id not in ids(db_session, SEEN + timedelta(days=2, hours=23))
    assert paper.id in ids(db_session, SEEN + timedelta(days=3, minutes=1))
