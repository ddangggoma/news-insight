from collections import Counter

from news_insight.strategy.personas import DEFAULT_PERSONA, PERSONA_KEYS, PERSONAS
from news_insight.strategy.schemas import PersonaInsight


def test_personas_by_group_with_the_readers_role_first() -> None:
    assert len(PERSONAS) == 31 and len(PERSONA_KEYS) == 31
    assert Counter(p.group for p in PERSONAS) == {
        "practitioner": 1,
        "executive": 4,
        "business": 6,
        "domain": 20,
    }
    assert PERSONAS[0].key == DEFAULT_PERSONA == "sensing_analyst"


def test_relevance_and_stances_are_lenient() -> None:
    insight = PersonaInsight.model_validate(
        {
            "key": "cto",
            "status": "insight",
            "relevance": "87.5",
            "stances": [
                {"theme": "ai__on_device_ai", "stance": "opportunity"},
                {"theme": "ai__on_device_ai", "stance": "risk"},
                {"theme": "not_a_theme", "stance": "risk"},
                {"theme": "semis__memory_storage", "stance": "bad"},
            ],
        }
    )
    assert insight.relevance == 87
    assert [s.theme for s in insight.stances] == ["ai__on_device_ai"]
    assert (
        PersonaInsight.model_validate(
            {"key": "x", "status": "no_signal", "relevance": None}
        ).relevance
        == 0
    )


def test_conflicts_pair_opportunity_and_risk_readings() -> None:
    from news_insight.public.briefings import BriefingPersona, stance_conflicts

    def persona(name: str, stance: str, status: str = "insight") -> BriefingPersona:
        return BriefingPersona(
            key=name,
            name=name,
            group="domain",
            status=status,
            headline="",
            insight="",
            actions=[],
            item_ids=[],
            stances=[{"theme": "xr", "stance": stance}],
        )

    conflicts = stance_conflicts(
        [persona("CFO", "risk"), persona("MX", "opportunity"), persona("Q", "risk", "no_signal")]
    )
    assert [(c.theme, c.opportunity, c.risk) for c in conflicts] == [("xr", ["MX"], ["CFO"])]
