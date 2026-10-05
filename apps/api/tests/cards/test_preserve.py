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
        ("OpenAI ships GPT-5 to 100 million users", "오픈AI, GPT-5를 1억 명에게 제공", []),
        (
            "OpenAI ships GPT-5 to 100 million users",
            "오픈AI, GPT-5를 많은 이용자에게 제공",
            ["100 million"],
        ),
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


@pytest.mark.parametrize(
    ("title", "title_ko", "missing"),
    [
        # 2026-10-05 audit: false alarms that hid 4,638 cards
        (
            "Popular Go frameworks https:// blog.jetbrains.com/go/2026/04/ 28/popular",
            "인기 Go 프레임워크",
            [],
        ),
        ("ald0405/whoop-data", "whoop-data: WHOOP 데이터 분석 도구", []),
        ("50万高端SUV音响PK：汽车音响哪个牌子音质最好", "50만 위안 고급 SUV 오디오 비교", []),
        ("【マイコン初心者必見】RL78で開発を始めよう！①", "RL78로 개발 시작하기", []),
        ("Official Gazette Notices for 02 November 2004", "2004년 11월 2일 관보 공고", []),
        ("What 81,000 people told us about AI economics", "8만 1천 명이 말한 AI 경제학", []),
        ("Deleting 800K Lines of Unit Tests", "단위 테스트 80만 줄 삭제", []),
        ("A Physics Professor Bet Me $10,000", "물리학 교수가 건 1만 달러 내기", []),
        ("Legacy 8-bit/16-bit microcontroller", "레거시 8비트/16비트 마이크로컨트롤러", []),
        ("Technical Sharing Session 3rd Anniversary", "테크니컬 셰어링 세션 3주년", []),
        ("1H26 Global Automotive LED Market", "2026년 상반기 글로벌 차량용 LED 시장", []),
        ("MeiG brings 7B-Class generative AI to the edge", "MeiG, 엣지에 7B급 생성형 AI", []),
        ("As COVID-19 forces conferences online", "코로나19로 학술대회가 온라인으로", []),
        ("MLCC Market Bulletin_20240711", "MLCC 시장 동향", []),
        ("Defense Tech News (vol.8) 2026 - 07 - 27", "국방 기술 뉴스 vol.8", []),
        ("Teuer und verlötet: der neue Mac Mini t3n.de", "비싸고 납땜된 신형 Mac Mini", []),
        # real losses still count
        ("민낯인데 이 정도?…49세 채정안", "배우 채정안 민낯 공개", ["49"]),
        ("Xiaomi Router 3G - 18.06.x / Wifi issues", "샤오미 라우터 3G 와이파이 문제", ["18.06.x"]),
    ],
)
def test_links_scripts_dates_and_korean_units(
    title: str, title_ko: str, missing: list[str]
) -> None:
    assert missing_facts(card(title), draft(title_ko)) == missing
