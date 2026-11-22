/** Community buzz clusters (화제 묶음) and breaking signals (속보): GET /api/public/buzz (2026-11-19). */

export interface BuzzPost {
  id: number;
  title: string;
  url: string;
  platform: string;
  author: string | null;
  first_seen_at: string;
}

export interface BuzzNews {
  id: number;
  title: string;
  url: string;
  source_name: string;
  first_seen_at: string;
}

export interface BuzzCluster {
  id: number;
  title: string;
  summary: string[];
  keywords: string[];
  summarized: boolean;
  breaking: boolean;
  breaking_at: string | null;
  is_event: boolean | null;
  lead_minutes: number | null;
  first_seen_at: string;
  last_seen_at: string;
  crossed_at: string;
  authors: number;
  posts: number;
  platforms: string[];
  heat: number;
  score: number;
  sample: BuzzPost[];
  news: BuzzNews[];
}

export interface BuzzView {
  generated_at: string;
  hours: number;
  clusters: BuzzCluster[];
}

const PLATFORM_LABEL: Record<string, string> = {
  fediverse: "Mastodon",
  hn: "Hacker News",
  bluesky: "Bluesky",
  threads: "Threads",
  v2ex: "V2EX",
  youtube: "YouTube",
  "dev community": "DEV",
  "stack exchange inc.": "Stack Exchange",
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABEL[platform] ?? platform;
}

/** "뉴스보다 1시간 20분 먼저", "뉴스보다 15분 먼저", or, before any news, "아직 뉴스 없음". */
export function leadLabel(cluster: Pick<BuzzCluster, "breaking" | "lead_minutes" | "news">): string | null {
  if (!cluster.breaking) return null;
  if (cluster.lead_minutes === null) return cluster.news.length ? null : "아직 뉴스 없음";
  const hours = Math.floor(cluster.lead_minutes / 60);
  const minutes = cluster.lead_minutes % 60;
  const span = hours ? `${hours}시간${minutes ? ` ${minutes}분` : ""}` : `${minutes}분`;
  return `뉴스보다 ${span} 먼저`;
}

/** Breaking first, then the rest as the API ordered them, at most `limit`. */
export function headline(clusters: BuzzCluster[], limit: number): BuzzCluster[] {
  return [...clusters.filter((c) => c.breaking), ...clusters.filter((c) => !c.breaking)].slice(0, limit);
}
