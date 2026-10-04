from collections import Counter

from news_insight.strategy.personas import PERSONA_KEYS, PERSONAS


def test_thirty_personas_by_group() -> None:
    assert len(PERSONAS) == 30 and len(PERSONA_KEYS) == 30
    assert Counter(p.group for p in PERSONAS) == {"executive": 4, "business": 6, "domain": 20}
