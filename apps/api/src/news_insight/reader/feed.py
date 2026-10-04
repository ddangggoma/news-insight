"""RSS 2.0 feeds: published briefings, or the latest cards of one taxonomy node."""

from datetime import datetime
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from news_insight.reader.schemas import ArchiveEntry, ReaderCard

TITLE = "Daily IT Intelligence"


def _channel(title: str, link: str, description: str) -> tuple[ET.Element, ET.Element]:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "ko"
    return rss, channel


def _item(
    channel: ET.Element, *, title: str, link: str, guid: str, description: str, when: datetime
) -> None:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = link
    ET.SubElement(item, "guid", isPermaLink="false").text = guid
    ET.SubElement(item, "description").text = description
    ET.SubElement(item, "pubDate").text = format_datetime(when)


def _render(rss: ET.Element) -> bytes:
    body: bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return body


def briefings_feed(entries: list[ArchiveEntry], *, base_url: str) -> bytes:
    base = base_url.rstrip("/")
    rss, channel = _channel(TITLE, base, "매일 05:00 KST 발행되는 근거 기반 DX 기술 브리핑")
    for entry in entries:
        _item(
            channel,
            title=f"{entry.briefing_date} · {entry.headline or '데일리 브리핑'}",
            link=f"{base}/briefings/{entry.briefing_date}",
            guid=f"briefing-{entry.briefing_date}-v{entry.version}",
            description=f"선정 기사 {entry.items}건",
            when=entry.published_at,
        )
    return _render(rss)


def cards_feed(cards: list[ReaderCard], *, base_url: str, label: str, link: str) -> bytes:
    rss, channel = _channel(f"{TITLE} · {label}", link, f"{label} 최신 카드")
    for card in cards:
        summary = " ".join(card.summary_ko)
        _item(
            channel,
            title=card.title_ko or card.title,
            link=card.url,
            guid=f"item-{card.id}",
            description=f"{summary} ({card.source_name})".strip(),
            when=card.published_at or card.first_seen_at,
        )
    return _render(rss)
