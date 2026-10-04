from news_insight.briefing.selection import Candidate, SelectionRules, shortlist


def cand(
    i: int,
    track: str = "news",
    category: str = "independent_media",
    region: str = "global_en",
    domain: str | None = None,
    score: float = 50.0,
) -> Candidate:
    return Candidate(i, track, category, region, domain or f"d{i}.com", score)


RULES = SelectionRules(
    size=10,
    track_min={"news": 4, "research_ip": 2, "oss": 1, "community": 1},
    domain_cap=0.2,
    korean_min=0.2,
    official_min=0.2,
    independent_min=0.2,
)


def test_minimums_are_met_before_filling_by_score() -> None:
    pool = [cand(i, score=100 - i) for i in range(20)]  # global independent news, top scores
    pool += [cand(100, region="kr", score=10), cand(101, region="kr", score=9)]
    pool += [
        cand(200, category="official_vendor", score=8),
        cand(201, category="government", score=7),
    ]
    pool += [
        cand(300, track="research_ip", category="academic_paper", score=6),
        cand(301, track="research_ip", category="academic_paper", score=5),
    ]
    pool += [
        cand(400, track="oss", category="oss_trend", score=4),
        cand(500, track="community", category="dev_forum", score=3),
    ]

    picked = shortlist(pool, RULES)
    ids = {c.item_id for c in picked}

    assert len(picked) == 10
    assert {100, 101, 200, 201, 300, 301, 400, 500} <= ids
    assert [c.track for c in picked][:2] == ["news", "news"]


def test_domain_cap_limits_any_single_publisher() -> None:
    pool = [cand(i, domain="same.com", score=100 - i) for i in range(10)] + [
        cand(50 + i) for i in range(10)
    ]

    picked = shortlist(
        pool,
        SelectionRules(
            size=10, track_min={}, domain_cap=0.2, korean_min=0, official_min=0, independent_min=0
        ),
    )

    assert sum(c.domain == "same.com" for c in picked) == 2
