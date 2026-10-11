import type { ProgressState } from "@/lib/types";

// engine groups in chart order (Antigravity's two quota groups count as one)
export const ENGINES = ["agy", "codex", "claude", "qwen", "reuse", "other"] as const;
const KNOWN = new Set<string>(ENGINES);

/** Engine name to its chart group: unknown engines count as "other". */
export function engineGroup(engine: string): (typeof ENGINES)[number] {
  return (KNOWN.has(engine) ? engine : "other") as (typeof ENGINES)[number];
}

export const STATE_LABEL: Record<ProgressState, string> = {
  ready: "완료",
  pending: "처리 대기",
  capped: "상한 대기",
  repeat: "복사 대기",
  failed: "실패(포기)",
  held: "보류(일시정지·퇴역)",
  archive: "아카이브(카드 제외)",
};
