import pytest

from news_insight.cards.preserve import missing_facts
from news_insight.cards.schemas import CardDraft, CardInput


def card(title: str) -> CardInput:
    return CardInput(id=1, title=title, source="s", language="en", excerpt=None)


def draft(title_ko: str, summary: list[str] | None = None) -> CardDraft:
    return CardDraft(id=1, title_ko=title_ko, summary_ko=summary or [], keywords=[])


@pytest.mark.parametrize(
    ("title", "title_ko", "missing"),
    [
        (
            "Samsung unveils Galaxy S30 with 40% faster NPU",
            "삼성, NPU 40% 빨라진 갤럭시 S30 공개",
            [],
        ),
        ("Nvidia H100 shipments hit 2,500 units", "엔비디아 H100 출하량 2,500대 돌파", []),
        ("OpenAI ships GPT-5 to 100 million users", "오픈AI, GPT-5를 1억 명에게 제공", ["100"]),
        ("Apple iPhone 18 Pro review", "애플 아이폰 프로 리뷰", ["18"]),
        ("Qualcomm X Elite 2 laptops", "퀄컴 X 엘리트 2 노트북", []),
        ("Wi-Fi 7 routers and 5G modems", "와이파이 7 공유기와 5G 모뎀", []),
        ("M5 MacBook Air benchmarks", "맥북 에어 벤치마크", ["M5"]),
    ],
)
def test_identifiers_and_numbers_must_survive(
    title: str, title_ko: str, missing: list[str]
) -> None:
    assert missing_facts(card(title), draft(title_ko)) == missing


def test_facts_may_live_in_the_summary() -> None:
    assert (
        missing_facts(
            card("TSMC N2 yields reach 70%"), draft("TSMC 수율 개선", ["N2 수율 70% 도달"])
        )
        == []
    )


@pytest.mark.parametrize(
    ("title", "title_ko", "missing"),
    [
        ("Samsung 3Q26 earnings beat", "삼성전자 3분기 실적 예상 상회", []),
        ("Apple Q4 iPhone sales", "애플 4분기 아이폰 판매", []),
        ("Inference 5x faster on NPU", "NPU 추론 5배 빨라져", []),
        ("Inference 2.5x faster", "추론 2.5배 향상", []),
        ("Samsung 3Q26 earnings beat", "삼성전자 실적 예상 상회", ["3Q26"]),
        ("Inference 5x faster on NPU", "NPU 추론 빨라져", ["5x"]),
    ],
)
def test_korean_quarter_and_multiplier_renderings(
    title: str, title_ko: str, missing: list[str]
) -> None:
    assert missing_facts(card(title), draft(title_ko)) == missing
