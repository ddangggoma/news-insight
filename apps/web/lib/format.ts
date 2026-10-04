import type { Outcome, Region, SourceStatus, Stage, Track } from "@/lib/types";

export const TRACK_LABEL: Record<Track, string> = {
  news: "뉴스·공식",
  community: "커뮤니티",
  research_ip: "논문·특허",
  oss: "오픈소스",
};

export const REGION_LABEL: Record<Region, string> = {
  kr: "한국",
  global_en: "글로벌(영어)",
  jp: "일본",
  greater_china: "중화권",
  eu_other: "유럽·기타",
};

export const STATUS_LABEL: Record<SourceStatus, string> = {
  candidate: "후보",
  active: "활성",
  paused: "일시정지",
  retired: "퇴역",
};

export const STAGE_LABEL: Record<Stage, string> = {
  unverified: "미검증",
  V0: "V0 정체성",
  V1: "V1 약관",
  V2: "V2 보안",
  V3: "V3 파서",
  V4: "V4 Canary",
  V5: "V5 품질",
  V6: "V6 활성",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  success: "성공",
  not_modified: "변경 없음",
  failed: "실패·재시도",
  dead_lettered: "DLQ",
  skipped: "건너뜀",
};

export const CATEGORY_LABEL: Record<string, string> = {
  independent_media: "독립 언론",
  official_vendor: "빅테크·제조사 공식",
  government: "정부·규제·표준",
  research_org: "연구기관·협회",
  dev_forum: "개발자 포럼",
  open_governance: "오픈 거버넌스",
  podcast_newsletter: "팟캐스트·뉴스레터",
  video_channel: "공식 영상",
  open_social: "공개 소셜",
  academic_paper: "논문",
  academic_index: "학술 색인",
  ip_office: "지식재산 기관",
  oss_trend: "오픈소스 트렌드",
  oss_release: "릴리스",
  oss_security: "보안 권고",
};

const DATE_TIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const DATE = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });
const NUMBER = new Intl.NumberFormat("ko-KR");
const RELATIVE = new Intl.RelativeTimeFormat("ko-KR", { numeric: "auto" });

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const parts = Object.fromEntries(DATE_TIME.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`;
}

/** "2026.09.14" in KST. */
export function formatDay(iso: string | null): string {
  if (!iso) return "—";
  const parts = Object.fromEntries(DATE.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.year}.${parts.month}.${parts.day}`;
}

export function formatRelative(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return RELATIVE.format(Math.round(seconds / size), unit);
  }
  return "방금";
}

export function formatNumber(value: number): string {
  return NUMBER.format(value);
}

export function formatPercent(ratio: number): string {
  return Number.isFinite(ratio) ? `${(ratio * 100).toFixed(1)}%` : "—";
}

const BRIEFING_DATE = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "UTC",
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
});

/** "2026-10-05" → "2026년 10월 5일 (월)" (a calendar date, so no time-zone shift). */
export function formatBriefingDate(day: string): string {
  const parts = Object.fromEntries(BRIEFING_DATE.formatToParts(new Date(`${day}T00:00:00Z`)).map((p) => [p.type, p.value]));
  return `${parts.year}년 ${parts.month} ${parts.day}일 (${parts.weekday})`;
}
