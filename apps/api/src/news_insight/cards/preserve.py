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


# Korean renderings that keep the fact: "3Q26"/"Q3" → "3분기", "5x" → "5배".
EQUIVALENTS = (
    (re.compile(r"^([1-4])Q(?:\d{2}|\d{4})?$", re.IGNORECASE), r"\1분기"),
    (re.compile(r"^Q([1-4])(?:\d{2}|\d{4})?$", re.IGNORECASE), r"\1분기"),
    (re.compile(r"^(\d+(?:\.\d+)?)x$", re.IGNORECASE), r"\1배"),
)


def _compact(text: str) -> str:
    return re.sub(r"[\s\-_.,·:]", "", text).casefold()


def _kept(token: str, target: str) -> bool:
    if _compact(token) in target:
        return True
    return any(
        pattern.match(token) and _compact(pattern.sub(korean, token)) in target
        for pattern, korean in EQUIVALENTS
    )


def missing_facts(card: CardInput, draft: CardDraft) -> list[str]:
    target = _compact(f"{draft.title_ko} {' '.join(draft.summary_ko)}")
    missing: list[str] = []
    for token in IDENTIFIER.findall(card.title):
        token = token.rstrip(".+-")
        if len(token) >= 2 and not _kept(token, target):
            missing.append(token)
    for number in NUMBER.findall(card.title):
        if _compact(number) not in target:
            missing.append(number)
    return list(dict.fromkeys(missing))
