"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TaxOp } from "@/lib/taxonomy-ops";

import type { ConsoleScheme } from "./model";

const ASSIGN = [["llm", "LLM"], ["rule", "규칙(별칭)"], ["derived", "파생(관계)"]] as const;
const USES = [["radar", "레이더"], ["filters", "필터"], ["watch", "관심 목록"], ["briefing", "브리핑"], ["personas", "페르소나"]] as const;
type Assign = "llm" | "rule" | "derived";

function SchemeFields({ value, onChange }: { value: Partial<ConsoleScheme> & { assign?: Assign[] }; onChange: (v: Partial<ConsoleScheme> & { assign?: Assign[] }) => void }) {
  const toggle = (list: string[] = [], item: string) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <label className="space-y-1 text-xs">
        <span className="text-muted-foreground">이름</span>
        <Input value={value.name ?? ""} onChange={(e) => onChange({ ...value, name: e.target.value })} className="h-8" />
      </label>
      <label className="space-y-1 text-xs">
        <span className="text-muted-foreground">깊이별 이름 (쉼표로, 예: 분야, 테마, 기술)</span>
        <Input value={(value.level_names ?? []).join(", ")} onChange={(e) => onChange({ ...value, level_names: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} className="h-8" />
      </label>
      <label className="space-y-1 text-xs">
        <span className="text-muted-foreground">LLM이 고르는 깊이</span>
        <Input type="number" min={1} max={10} value={value.llm_depth ?? 1} onChange={(e) => onChange({ ...value, llm_depth: Number(e.target.value) })} className="h-8" />
      </label>
      <label className="space-y-1 text-xs">
        <span className="text-muted-foreground">카드당 최대 개수</span>
        <Input type="number" min={1} max={10} value={value.max_labels ?? 2} onChange={(e) => onChange({ ...value, max_labels: Number(e.target.value) })} className="h-8" />
      </label>
      <fieldset className="space-y-1 text-xs">
        <legend className="text-muted-foreground">붙이는 방법</legend>
        {ASSIGN.map(([k, l]) => (
          <label key={k} className="mr-3 inline-flex items-center gap-1">
            <input type="checkbox" checked={(value.assign ?? []).includes(k)} onChange={() => onChange({ ...value, assign: toggle(value.assign, k) as Assign[] })} /> {l}
          </label>
        ))}
      </fieldset>
      <fieldset className="space-y-1 text-xs">
        <legend className="text-muted-foreground">쓰는 곳</legend>
        {USES.map(([k, l]) => (
          <label key={k} className="mr-3 inline-flex items-center gap-1">
            <input type="checkbox" checked={(value.uses ?? []).includes(k)} onChange={() => onChange({ ...value, uses: toggle(value.uses, k) })} /> {l}
          </label>
        ))}
      </fieldset>
    </div>
  );
}

/** The selected scheme's settings, and a form for a new scheme. */
export function SchemePanel({ scheme, assign, onAdd }: { scheme: ConsoleScheme; assign: Assign[]; onAdd: (op: TaxOp) => void }) {
  const [edit, setEdit] = useState<Partial<ConsoleScheme> & { assign?: Assign[] }>({ ...scheme, assign });
  const [requeue, setRequeue] = useState(false);
  const [draft, setDraft] = useState<Partial<ConsoleScheme> & { assign?: Assign[]; key?: string }>({ name: "", structure: "list", llm_depth: 1, max_labels: 2, assign: ["llm"], uses: ["filters"], level_names: [] });
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="font-semibold">{scheme.name} 설정</h2>
        <SchemeFields value={edit} onChange={setEdit} />
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={requeue} onChange={(e) => setRequeue(e.target.checked)} /> LLM 깊이·개수를 바꾸면 이 체계의 카드를 다시 분류
        </label>
        <Button
          size="sm"
          onClick={() =>
            onAdd({
              op: "update_scheme",
              key: scheme.key,
              name: edit.name,
              level_names: edit.level_names,
              llm_depth: edit.llm_depth ?? undefined,
              max_labels: edit.max_labels,
              assign: edit.assign,
              uses: edit.uses,
              requeue,
            })
          }
        >
          설정 수정을 변경에 추가
        </Button>
      </section>
      <section className="space-y-2 border-t pt-4">
        <h2 className="font-semibold">새 체계</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">키 (영문 소문자·숫자·_)</span>
            <Input value={draft.key ?? ""} onChange={(e) => setDraft({ ...draft, key: e.target.value })} placeholder="domain" className="h-8" />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">구조</span>
            <select value={draft.structure} onChange={(e) => setDraft({ ...draft, structure: e.target.value as "tree" | "list" })} className="h-8 w-full rounded-md border bg-background px-2 text-sm">
              <option value="list">목록 (깊이 1)</option>
              <option value="tree">트리 (깊이 자유)</option>
            </select>
          </label>
        </div>
        <SchemeFields value={draft} onChange={(v) => setDraft({ ...draft, ...v })} />
        <Button
          size="sm"
          disabled={!draft.key || !draft.name}
          onClick={() =>
            onAdd({
              op: "create_scheme",
              key: draft.key ?? "",
              name: draft.name ?? "",
              structure: draft.structure ?? "list",
              llm_depth: draft.llm_depth ?? 1,
              max_labels: draft.max_labels ?? 2,
              assign: draft.assign,
              uses: draft.uses,
              level_names: draft.level_names,
            })
          }
        >
          체계 추가를 변경에 넣기
        </Button>
      </section>
    </div>
  );
}
