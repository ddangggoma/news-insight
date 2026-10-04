"""Fact preservation check for Korean cards (requirements §6).

The Korean title must keep the original title's identifiers (model names, versions: S30,
H100, GPT-5, 5G) and its multi-digit numbers and percentages. A card that loses one is
rejected for this attempt; after MAX_ATTEMPTS the console falls back to the original title.
"""

import re

from news_insight.cards.schemas import CardDraft, CardInput

IDENTIFIER = re.compile(
    r"(?<![\w.])(?=[\w.+-]*\d)(?=[\w.+-]*[A-Za-z])[A-Za-z0-9][\w.+-]{1,24}(?![\w])"
)
NUMBER = re.compile(
    r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])\d{2,}(?:\.\d+)?%?|\d+(?:\.\d+)?%"
)


def _compact(text: str) -> str:
    return re.sub(r"[\s\-_.,·:]", "", text).casefold()


def missing_facts(card: CardInput, draft: CardDraft) -> list[str]:
    target = _compact(f"{draft.title_ko} {' '.join(draft.summary_ko)}")
    missing: list[str] = []
    for token in IDENTIFIER.findall(card.title):
        token = token.rstrip(".+-")
        if len(token) >= 2 and _compact(token) not in target:
            missing.append(token)
    for number in NUMBER.findall(card.title):
        if _compact(number) not in target:
            missing.append(number)
    return list(dict.fromkeys(missing))
