"""One key per technology across card engines and languages.

Card keywords are free text, so "AI 에이전트", "AI에이전트" and "AI-Agent" would count as three
technologies. Since checklist KW-1 the canonical keys are computed when a card is written
(`ItemCard.technology_keys`, technology registry) and the radar groups on that GIN-indexed
array. Labels come from the registry, then from the most common spelling (`keyword_labels`).
"""

from typing import Any

from sqlalchemy import func

from news_insight.cards.models import ItemCard
from news_insight.technologies.catalog import normalize, seed_alias_map


def keyword_key(text: str) -> str:
    """Python twin for fixtures, tests and URL checks (bundled seed aliases)."""
    key = normalize(text)
    return seed_alias_map().get(key, key)


def keyword_element(name: str) -> Any:
    """Lateral set of a card's canonical keyword keys."""
    return (
        func.jsonb_array_elements_text(ItemCard.technology_keys).table_valued("value").lateral(name)
    )
