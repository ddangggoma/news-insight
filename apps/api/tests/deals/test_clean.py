from datetime import date

import pytest

from news_insight.deals.clean import USD, checked_amount, fold, key_for, same_party, stage
from news_insight.deals.models import Deal
from news_insight.deals.views import dedupe


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Warner Bros. Discovery", "Warner Bros Discovery", True),
        ("Warner", "Warner Bros. Discovery", True),
        ("Paramount Inc.", "Paramount", True),
        ("Character.AI", "Character.ai", True),
        ("TypeSafe", "TypeSafe AI", True),
        ("워너 브라더스", "워너브러더스 디스커버리", True),
        ("(주)인텔리빅스", "인텔리빅스", True),
        ("Meta", "Metaplanet", False),  # a prefix that is not a whole word
        ("Arm", "Armada", False),
        ("Paramount", "파라마운트", False),  # other scripts: only the registry can tell
    ],
)
def test_party_spellings(a: str, b: str, same: bool) -> None:
    assert same_party(a, b) is same


def test_registry_keys_from_folded_and_parenthesised_names() -> None:
    aliases = {"amazon": "amazon", "aws": "amazon", "lgelectronics": "lg_electronics"}
    assert key_for("Amazon Web Services (AWS)", aliases) == "amazon"
    assert key_for("Amazon, Inc.", aliases) == "amazon"
    assert key_for("LG Electronics Co., Ltd.", aliases) == "lg_electronics"
    assert key_for("Huxe", aliases) is None and key_for(None, aliases) is None
    assert fold("Warner Bros.") == fold("warner brothers")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Series B", "시리즈 B"),
        ("시리즈B", "시리즈 B"),
        ("시리즈 B", "시리즈 B"),
        ("B라운드", "시리즈 B"),
        ("시리즈 C-2", "시리즈 C-2"),
        ("시리즈 A 브릿지", "시리즈 A 브릿지"),
        ("시리즈 F (IPO 전)", "시리즈 F"),
        ("Pre-A+", "프리 시리즈 A+"),
        ("시리즈 프리A", "프리 시리즈 A"),
        ("Seed", "시드"),
        ("Pre-seed", "프리시드"),
        ("Angel Round", "엔젤"),
        ("Strategic Investment", "전략적 투자"),
        ("업무협약(MOU)", "MOU"),
        ("MOU 체결", "MOU"),
        ("시리즈 B (추정, 기사에 명시된 라운드 없음)", None),
        ("미상", None),
        ("", None),
        ("인재 인수(Acqui-hire)", "인재 인수(Acqui-hire)"),
    ],
)
def test_one_spelling_per_stage(raw: str, clean: str | None) -> None:
    assert stage(raw) == clean


def test_rates_cover_the_currencies_seen() -> None:
    assert {"MYR", "CAD", "KRW", "CNY", "EUR"} <= set(USD)


@pytest.mark.parametrize(
    ("amount", "kind", "currency", "summary", "expected"),
    [
        # a misread 억: the summary keeps the article's units
        (337e9, "investment", "EUR", "AWS가 아라곤 인프라에 337억 유로를 투자한다.", 33.7e9),
        (13e9, "investment", "USD", "이 중 13억 달러 규모의 기간대출을 인수했다.", 1.3e9),
        (30e9, "acquisition", "KRW", "수이가 지분을 약 3천억 원에 인수했다.", 3e11),
        (2.08e13, "investment", "KRW", "인도에 약 20조 8천억 원을 투자한다.", 2.08e13),
        # a valuation is not the money raised
        (2e12, "ipo", "USD", "Anthropic이 기업가치 2조 달러 이상을 목표로 S-1을 제출했다.", None),
        (4e8, "investment", "USD", "기업가치를 약 4억 달러로 평가받았다.", None),
        # ... but a figure next to one is
        (870e6, "investment", "USD", "기업가치 75억 달러 기준 8억 7,000만 달러를 유치했다.", 870e6),
        (750e6, "investment", "USD", "157.5억 달러 기업가치로 7억 5000만 달러를 유치했다.", 750e6),
        # an acquisition's valuation is its price
        (675e6, "acquisition", "USD", "OnLogic을 기업가치 6억 7,500만 달러에 인수한다.", 675e6),
        # beyond what one deal of the kind moves
        (134e12, "ipo", "KRW", "Solidigm이 최대 134조 원 규모 미국 IPO를 추진한다.", None),
        (200e9, "investment", "USD", "약 2,000억 달러를 인프라에 투입할 계획이다.", None),
        (111e9, "acquisition", "USD", "1,110억 달러에 워너 브라더스를 인수했다.", 111e9),
        # figures in another currency or that are not money moved are no reference
        (1e12, "investment", "KRW", "KKR에 10억 달러(약 1조 4,000억 원)를 투자한다.", 1e12),
        (1e12, "ipo", "KRW", "청약에 10조 원 이상의 증거금이 몰렸다.", 1e12),
        (11.7e6, "investment", "CAD", "1,170만 캐나다달러 규모의 투자 약정", 11.7e6),
        (134, "ipo", "KRW", "", None),  # the unit was lost
        (None, "investment", "USD", "", None),
    ],
)
def test_amount_plausibility(
    amount: float | None, kind: str, currency: str, summary: str, expected: float | None
) -> None:
    assert checked_amount(amount, kind=kind, currency=currency, summary=summary) == expected


def test_the_valuation_the_model_reports_is_not_the_amount() -> None:
    args = {"kind": "investment", "currency": "USD", "summary": "X가 투자를 유치했다."}
    assert checked_amount(5e9, valuation=5e9, **args) is None  # type: ignore[arg-type]
    assert checked_amount(5e8, valuation=5e9, **args) == 5e8  # type: ignore[arg-type]


def deal(i: int, actor: str, target: str | None, usd: float | None, day: int, **kw: str) -> Deal:
    return Deal(
        id=i,
        kind=kw.get("kind", "acquisition"),
        actor=actor,
        actor_key=kw.get("actor_key"),
        counterparty=target,
        counterparty_key=kw.get("key"),
        amount_usd=usd,
        announced_on=date(2026, 10, day),
    )


def rows(*deals: Deal) -> list[tuple[Deal, str, str, str]]:
    return [(d, "t", "s", "u") for d in sorted(deals, key=lambda d: -d.id)]


def test_one_deal_under_many_names_is_one_row() -> None:
    """Audit 2026-10-27: Paramount–Warner was 11 rows under five spellings."""
    merged = dedupe(
        rows(
            deal(1, "Paramount", "Warner Bros. Discovery", 111e9, 7),
            deal(2, "Paramount", "Warner", 111e9, 7),
            deal(3, "파라마운트", "워너 브라더스", 111e9, 7),
            deal(4, "派拉蒙", "时代华纳", 110e9, 9),
            deal(5, "파라마운트 스카이댄스", "워너브러더스 디스커버리", 110e9, 9),
            deal(6, "Paramount", "Warner Bros Discovery", None, 7),  # unsized: joins the one fit
        )
    )
    assert [m[-1] for m in merged] == [6]
    assert merged[0][0].id == 1  # the earliest sized report with a named actor leads


def test_different_deals_stay_apart() -> None:
    merged = dedupe(
        rows(
            # round amounts in the same weeks, names in one script: two deals
            deal(1, "미공개", "Isomorphic Labs", 40e9, 7, kind="investment"),
            deal(2, "Apollo", "SpaceX", 40e9, 8, kind="investment"),
            # a registered company is matched through its aliases, not by amount
            deal(3, "Nvidia", "Anthropic", 10e9, 7, kind="investment", key="anthropic"),
            deal(4, "미공개", "블루오리진", 10e9, 8, kind="investment"),
            # same target, far apart in size or time
            deal(5, "a16z", "TypeSafe AI", 870e6, 7, kind="investment"),
            deal(6, "미공개", "TypeSafe", 3e9, 8, kind="investment"),
            deal(7, "Sequoia", "TypeSafe AI", 880e6, 30, kind="investment"),
            # a word prefix is not a name prefix
            deal(8, "Apple", "Meta", None, 7, kind="partnership"),
            deal(9, "Apple", "Metaplanet", None, 7, kind="partnership"),
        )
    )
    assert len(merged) == 9


def test_an_unsized_report_waits_when_two_groups_fit() -> None:
    merged = dedupe(
        rows(
            deal(1, "a16z", "TypeSafe AI", 870e6, 7, kind="investment"),
            deal(2, "Nvidia", "TypeSafe AI", 30e6, 8, kind="investment"),
            deal(3, "미공개", "TypeSafe", None, 8, kind="investment"),
        )
    )
    assert sorted(m[-1] for m in merged) == [1, 1, 1]


def test_registry_keys_tie_spellings_in_any_script() -> None:
    merged = dedupe(
        rows(
            deal(1, "SK텔레콤", "업스테이지", None, 7, kind="partnership", actor_key="skt"),
            deal(2, "SK Telecom", "Upstage", None, 8, kind="partnership", actor_key="skt"),
        )
    )
    assert [m[-1] for m in merged] == [1, 1]  # 업스테이지 / Upstage: not in the registry
    merged = dedupe(
        rows(
            deal(
                1, "SK텔레콤", "업스테이지", None, 7, kind="partnership", actor_key="skt", key="up"
            ),
            deal(
                2, "SK Telecom", "Upstage", None, 8, kind="partnership", actor_key="skt", key="up"
            ),
        )
    )
    assert [m[-1] for m in merged] == [2]
