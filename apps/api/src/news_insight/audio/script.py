"""The spoken briefing's script, assembled from the published briefing (plan 13 A1).

No model writes it: it reads the briefing's own three lines, insights, watch list hits and
company moves in a fixed order, so the audio never says anything the page does not.
"""

import re
from datetime import date

from news_insight.public.briefings import PublicBriefing

ORDINAL = ("첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째", "일곱째", "여덟째")
URL = re.compile(r"https?://\S+")
SPACES = re.compile(r"\s+")


def speakable(text: str) -> str:
    """Strip what a voice reads badly: links, bullets, middle dots and slashes."""
    text = URL.sub("", text)
    text = text.replace("·", ", ").replace("/", " ").replace("→", ", ").replace("~", "에서 ")
    text = re.sub(r"[#*_>\[\]]", "", text)
    return SPACES.sub(" ", text).strip()


def _sentence(text: str) -> str:
    text = speakable(text)
    return text if not text or text[-1] in ".?!" else f"{text}."


def _day(value: date) -> str:
    return f"{value.month}월 {value.day}일"


def build_script(briefing: PublicBriefing) -> str:
    lines = [f"{_day(briefing.briefing_date)} 데일리 브리핑입니다."]
    if briefing.headline:
        lines.append(_sentence(briefing.headline))
    tldr = briefing.tldr or [insight.title for insight in briefing.insights[:3]]
    if tldr:
        lines.append(f"오늘의 핵심 {len(tldr)}가지입니다.")
        lines += [f"{ORDINAL[i]}, {_sentence(text)}" for i, text in enumerate(tldr[:3])]
    if briefing.watch:
        hits = ", ".join(f"{hit.label} {hit.count}건" for hit in briefing.watch[:5])
        lines.append(f"관심 항목 소식입니다. {hits}이 보도됐습니다.")
    if briefing.insights:
        lines.append("이어서 인사이트를 자세히 전합니다.")
        for index, insight in enumerate(briefing.insights[: len(ORDINAL)]):
            lines.append(f"{ORDINAL[index]} 인사이트, {_sentence(insight.title)}")
            lines.append(_sentence(insight.body))
    moves = [m.label for m in briefing.companies[:5]]
    if moves:
        lines.append(f"오늘 많이 언급된 기업은 {', '.join(moves)}입니다.")
    lines.append("근거 기사는 브리핑 페이지에서 확인하세요. 이상 오늘의 브리핑이었습니다.")
    return "\n".join(line for line in lines if line)
