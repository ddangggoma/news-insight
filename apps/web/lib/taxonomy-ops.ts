// Change operations for the console's taxonomy workspace (plan 15-5), mirroring the API's
// change engine (apps/api/src/news_insight/taxonomy/changes.py).

export type TaxOp =
  | { op: "create_node"; scheme: string; key: string; label: string; parent?: string | null; definition?: string | null; aliases?: string[]; requeue?: boolean }
  | { op: "update_node"; scheme: string; key: string; label?: string; definition?: string | null; include_text?: string | null; exclude_text?: string | null; aliases?: string[]; sort?: number; status?: "active" | "deprecated" }
  | { op: "move_node"; scheme: string; key: string; parent: string | null; requeue?: boolean }
  | { op: "merge_node"; scheme: string; key: string; into: string }
  | { op: "retire_node"; scheme: string; key: string; replacement?: string | null }
  | { op: "split_node"; scheme: string; key: string; parts: { key: string; label: string; aliases?: string[] }[] }
  | { op: "create_scheme"; key: string; name: string; structure: "tree" | "list"; description?: string | null; min_labels?: number; max_labels?: number; llm_depth?: number | null; assign?: ("llm" | "rule" | "derived")[]; uses?: string[]; level_names?: string[] }
  | { op: "update_scheme"; key: string; name?: string; description?: string | null; min_labels?: number; max_labels?: number; llm_depth?: number; assign?: ("llm" | "rule" | "derived")[]; uses?: string[]; level_names?: string[]; requeue?: boolean }
  | { op: "add_relation" | "remove_relation"; from_scheme: string; from_key: string; to_scheme: string; to_key: string; kind?: "implies" | "related" };

export interface OpOutcome {
  op: string;
  summary: string;
  cards: number;
  requeued: number;
  warnings: string[];
}

export interface ChangeResult {
  revision_id: number | null;
  outcomes: OpOutcome[];
  affected_cards: number;
  requeued_cards: number;
  eta_hours: number | null;
  prompt_tokens: number;
  prompt_over_budget: boolean;
  samples: { item_id: number; title: string | null }[];
}

export interface Revision {
  id: number;
  created_at: string;
  author: string | null;
  note: string | null;
  status: "applied" | "rolled_back" | "draft";
  ops: TaxOp[];
}

export type Labeler = (scheme: string, key: string) => string;

/** One Korean line per operation, with node names where known. */
export function describe(op: TaxOp, label: Labeler): string {
  switch (op.op) {
    case "create_node":
      return `추가: ${op.label}${op.parent ? ` (상위 ${label(op.scheme, op.parent)})` : " (최상위)"}${op.requeue ? " · 재분류" : ""}`;
    case "update_node": {
      const fields = Object.keys(op).filter((k) => !["op", "scheme", "key"].includes(k));
      if (op.status === "deprecated") return `비활성화: ${label(op.scheme, op.key)}`;
      if (op.label) return `이름 변경: ${label(op.scheme, op.key)} → ${op.label}`;
      return `수정: ${label(op.scheme, op.key)} (${fields.join(", ")})`;
    }
    case "move_node":
      return `이동: ${label(op.scheme, op.key)} → ${op.parent ? label(op.scheme, op.parent) : "최상위"}${op.requeue ? " · 재분류" : ""}`;
    case "merge_node":
      return `통합: ${label(op.scheme, op.key)} → ${label(op.scheme, op.into)}`;
    case "retire_node":
      return `폐지: ${label(op.scheme, op.key)}${op.replacement ? ` → ${label(op.scheme, op.replacement)}` : ""}`;
    case "split_node":
      return `분할: ${label(op.scheme, op.key)} → ${op.parts.map((p) => p.label).join(", ")} · 재분류`;
    case "create_scheme":
      return `체계 추가: ${op.name} (${op.structure === "tree" ? "트리" : "목록"})`;
    case "update_scheme":
      return `체계 수정: ${op.key} (${Object.keys(op).filter((k) => !["op", "key"].includes(k)).join(", ")})`;
    case "add_relation":
      return `관계 추가: ${label(op.from_scheme, op.from_key)} → ${label(op.to_scheme, op.to_key)}`;
    case "remove_relation":
      return `관계 삭제: ${label(op.from_scheme, op.from_key)} ↛ ${label(op.to_scheme, op.to_key)}`;
  }
}

/** A key from a label: lower case, spaces to hyphens, safe characters only (the API checks again). */
export function suggestKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[\s·/]+/g, "-")
    .replace(/[^a-z0-9가-힣_\-.]/g, "")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}
