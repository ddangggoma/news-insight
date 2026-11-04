"""Site placeholders and boilerplate that are not article text.

A feed or page often fills `summary` with something that is no content at all: Hacker News and
Lobsters send "Comments", a CMS sends "None" or "null", a page extractor returns a single
character or a hashtag line, InfoQ 中文 sends "点击查看原文>". 2026-10-27 card audit (K01):
732 cards were written from such text, and the engine invented a summary for it.

`is_placeholder` is the one judgement of "this is no text"; `usable_text` picks the first real
text of an item; `has_text` is the same judgement in SQL (card queues and donor selection).
`strip_boilerplate` is for duplicate keys (K08): a social post whose text is a label
("Source: BleepingComputer Read: <link>"), a publisher tag and hashtags says nothing about the
story, so equal boilerplate must not make two posts repeats of each other.
"""

import re
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

# One pattern, written in the syntax shared by Python `re` and PostgreSQL ARE (`~*`), matched
# against the whole text, case-insensitive. Alternatives:
#   1. nothing but punctuation, symbols and spaces: "", "(", "...", "…", "。"
#   2. nothing but hashtags / mentions: "# infosec # cybersecurity", "#ai #ia #chatgpt"
#   3. one ASCII word or code: "Comments", "None", "null", "robotics", "text-generation"
#      (a model-hub pipeline tag or a category name, never a sentence)
#   4. known boilerplate phrases
PLACEHOLDER_PATTERN = (
    r"^\s*(?:"
    r"[\s\-_.…()\[\]{}<>:;,!?*#@/|\"'`~+=。、，！？＞》]*"
    r"|(?:[#@]\s*[^\s#@]+\s*)+"
    r"|[a-z0-9_.:+-]{1,40}"
    r"|n/a|no (?:description|content|summary|text)|no description available"
    r"|(?:read|view|see) (?:more|full (?:article|story|topic|post)|original)\.*"
    r"|continue reading\.*|click (?:here )?to (?:read|view)(?: more)?\.*"
    r"|originally published at\.*"
    r"|\(topic deleted by author\).*"
    r"|product type page"
    r"|点击查看原文>?|查看原文>?|阅读原文>?|閱讀原文>?|內文連結|内文链接|早安。?"
    r"|원문 ?보기|여기를 눌러 링크를 확인하세요|출처"
    r")\s*$"
)
_PLACEHOLDER = re.compile(PLACEHOLDER_PATTERN, re.IGNORECASE)


def is_placeholder(text: str | None) -> bool:
    """True when the text is empty or only a site placeholder: it says nothing about the item."""
    return text is None or _PLACEHOLDER.match(text) is not None


def usable_text(*texts: str | None) -> str | None:
    """The first of the texts (summary, then body) that is real; None when none is."""
    for text in texts:
        if not is_placeholder(text):
            return text
    return None


def has_text(summary: Any, body: Any) -> ColumnElement[bool]:
    """SQL twin of `usable_text(summary, body) is not None` for two text columns."""

    def real(column: Any) -> ColumnElement[bool]:
        return and_(column.is_not(None), column.op("!~*")(PLACEHOLDER_PATTERN))

    return or_(real(summary), real(body))


# A post that only labels the link it shares: "Source: BleepingComputer Read: https://…" (the
# title is cut at a fixed length, so the label may end in an ellipsis instead of "Read:").
_SOURCE_LABEL = re.compile(r"^\s*source:\s[^:]{1,100}?(?:\sread:|…\s*$)", re.IGNORECASE)
_TAIL = re.compile(r"\bmore cyber news\b.*", re.IGNORECASE | re.DOTALL)
_HASHTAGS = re.compile(r"[#@]\s*\w+")


def strip_boilerplate(text: str | None) -> str:
    """The text without a source label, hashtags and a "more news" tail (for duplicate keys)."""
    if not text:
        return ""
    text = _SOURCE_LABEL.sub(" ", text)
    text = _TAIL.sub(" ", text)
    return _HASHTAGS.sub(" ", text)
