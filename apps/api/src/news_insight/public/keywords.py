"""One key per technology across card engines and languages.

Card keywords are free text, so "AI 에이전트", "AI에이전트" and "AI-Agent" would count as three
technologies. Keys drop case, spaces, hyphens, underscores and middle dots, then map known
synonyms and translations to one canonical key. Add a pair to ALIASES when the radar shows the
same technology split in two; the canonical key is what URLs and the radar use.
"""

import re
from typing import Any

from sqlalchemy import func, literal
from sqlalchemy.dialects.postgresql import JSONB

STRIP = r"[\s\-_·]"

# canonical key → other spellings (already stripped and lower-cased)
ALIASES: dict[str, tuple[str, ...]] = {
    "llm": (
        "대형언어모델",
        "거대언어모델",
        "대규모언어모델",
        "largelanguagemodel",
        "largelanguagemodels",
    ),
    "slm": ("소형언어모델", "소규모언어모델", "smalllanguagemodel", "smalllanguagemodels"),
    "생성형ai": ("generativeai", "genai", "생성ai", "생성인공지능"),
    "ai에이전트": ("aiagent", "aiagents", "에이전트ai"),
    "에이전틱ai": ("agenticai",),
    "온디바이스ai": ("ondeviceai", "ondevice", "엣지ai", "edgeai"),
    "mcp": ("modelcontextprotocol",),
    "rag": ("검색증강생성", "retrievalaugmentedgeneration"),
    "멀티모달": ("multimodal", "멀티모달ai", "multimodalai"),
    "vla모델": ("vla", "visionlanguageaction", "visionlanguageactionmodel"),
    "hbm": ("고대역폭메모리", "highbandwidthmemory"),
    "cxl": ("computeexpresslink",),
    "npu": ("신경망처리장치", "neuralprocessingunit"),
    "칩렛": ("chiplet", "chiplets"),
    "6g": ("6세대이동통신", "6thgeneration"),
    "ntn": ("비지상네트워크", "nonterrestrialnetwork", "위성직접통신"),
    "휴머노이드": ("humanoid", "humanoidrobot", "humanoidrobots", "휴머노이드로봇"),
    "자율주행": ("autonomousdriving", "selfdriving", "자율주행차"),
    "디지털트윈": ("digitaltwin", "digitaltwins"),
    "양자컴퓨터": ("양자컴퓨팅", "quantumcomputing", "quantumcomputer"),
    "포스트양자암호": ("pqc", "postquantumcryptography", "양자내성암호"),
    "xr": ("확장현실", "extendedreality"),
    "스마트글래스": ("smartglasses", "ai글래스", "aiglasses"),
    "전고체배터리": ("solidstatebattery", "allsolidstatebattery"),
    "마이크로led": ("microled",),
    "euaiact": ("eu인공지능법", "유럽연합ai법", "eu인공지능규제법"),
    "ai기본법": ("인공지능기본법",),
    "코딩에이전트": ("codingagent", "codingagents", "ai코딩에이전트"),
    "바이브코딩": ("vibecoding",),
}
ALIAS_MAP: dict[str, str] = {
    alias: canonical for canonical, aliases in ALIASES.items() for alias in aliases
}


def keyword_key(text: str) -> str:
    """Python twin of `keyword_key_sql` for fixtures, tests and URL checks."""
    stripped = re.sub(STRIP, "", text.lower())
    return ALIAS_MAP.get(stripped, stripped)


def keyword_key_sql(value: Any) -> Any:
    """SQL expression giving the canonical key of a keyword column or JSON array element.

    Build it once per statement and reuse the object in SELECT, WHERE and GROUP BY so the
    rendered expression (and its bound parameters) is identical in every clause.
    """
    stripped = func.regexp_replace(func.lower(value), STRIP, "", "g")
    return func.coalesce(literal(ALIAS_MAP, JSONB).op("->>")(stripped), stripped)
