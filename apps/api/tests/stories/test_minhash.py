from news_insight.stories.minhash import (
    band_hashes,
    dedup_url,
    shingles,
    signature,
    similarity,
)


def sig(text: str) -> list[int]:
    return signature(shingles(text))


def test_similar_titles_score_high_and_unrelated_low() -> None:
    a = sig("삼성전자, 갤럭시 S30 공개…온디바이스 AI 탑재")
    b = sig("삼성전자 갤럭시 S30 공개, 온디바이스 AI 탑재했다")
    c = sig("LG디스플레이 2세대 탠덤 OLED 양산 돌입")

    assert similarity(a, b) > 0.6
    assert similarity(a, c) < 0.2
    assert similarity(a, a) == 1.0


def test_near_duplicates_share_an_lsh_band() -> None:
    a = band_hashes(sig("Apple unveils iPhone 18 Pro with new camera system"))
    b = band_hashes(sig("Apple unveils iPhone 18 Pro with a new camera system"))

    assert any(x == y for x, y in zip(a, b, strict=True))
    assert all(0 <= value < 2**63 for value in a)


def test_dedup_url_unifies_amp_and_mobile_variants() -> None:
    base = dedup_url("https://www.example.com/news/123")

    assert dedup_url("https://m.example.com/news/123/amp") == base
    assert dedup_url("https://example.com/amp/news/123?outputType=amp&utm_source=x") == base
    assert dedup_url("https://www.example.com/news/124") != base
