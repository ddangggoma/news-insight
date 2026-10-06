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
