import type { AudioEntry } from "@/lib/briefing-types";
import type { DigestSummary } from "@/lib/types";

function escapeXml(value: string): string {
  return value.replace(/[<>&'"]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[char] ?? char);
}

/** RSS 2.0 feed of published digests, newest first. */
export function digestFeed(origin: string, digests: DigestSummary[]): string {
  const items = digests
    .map((digest) => {
      const link = `${origin}/briefings/${digest.digest_date}`;
      return [
        "<item>",
        `<title>${escapeXml(`${digest.digest_date} · ${digest.headline}`)}</title>`,
        `<link>${escapeXml(link)}</link>`,
        `<guid isPermaLink="true">${escapeXml(link)}</guid>`,
        `<pubDate>${new Date(digest.generated_at).toUTCString()}</pubDate>`,
        `<description>${escapeXml(`${digest.headline} (기사 ${digest.item_count}건 분석)`)}</description>`,
        "</item>",
      ].join("");
    })
    .join("");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0"><channel>',
    "<title>DX 인텔리전스 데일리 다이제스트</title>",
    `<link>${escapeXml(origin)}/digests</link>`,
    "<description>매일 05:00 KST 발행되는 근거 기반 DX 기술 다이제스트</description>",
    "<language>ko</language>",
    items,
    "</channel></rss>",
  ].join("");
}

function duration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Podcast RSS of the spoken daily briefings (plan 13 A1), newest first. */
export function podcastFeed(origin: string, entries: AudioEntry[]): string {
  const items = entries
    .map((entry) => {
      const link = `${origin}/briefings/${entry.briefing_date}`;
      return [
        "<item>",
        `<title>${escapeXml(`${entry.briefing_date} · ${entry.headline}`)}</title>`,
        `<link>${escapeXml(link)}</link>`,
        `<guid isPermaLink="false">${escapeXml(entry.url)}</guid>`,
        `<pubDate>${new Date(entry.generated_at).toUTCString()}</pubDate>`,
        `<enclosure url="${escapeXml(origin + entry.url)}" length="${entry.bytes}" type="audio/mp4"/>`,
        `<itunes:duration>${duration(entry.seconds)}</itunes:duration>`,
        `<description>${escapeXml(entry.headline)}</description>`,
        "</item>",
      ].join("");
    })
    .join("");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>',
    "<title>DX 인텔리전스 데일리 브리핑 (오디오)</title>",
    `<link>${escapeXml(origin)}/briefings</link>`,
    "<description>매일 아침 발행되는 DX 기술 브리핑을 음성으로 듣습니다. 근거 기사는 브리핑 페이지에 있습니다.</description>",
    "<language>ko</language>",
    "<itunes:explicit>false</itunes:explicit>",
    items,
    "</channel></rss>",
  ].join("");
}
