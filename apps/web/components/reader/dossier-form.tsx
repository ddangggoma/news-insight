"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { type FormState, saveDossier } from "@/app/(reader)/dossiers/actions";
import { Button } from "@/components/ui/button";
import type { ScopeOption } from "@/lib/ask-types";
import type { DossierDetail } from "@/lib/dossier-types";

const field = "w-full rounded-md border bg-background px-3 py-2 text-sm";
const SIMILARITY = [
  { value: 0.55, label: "넓게 (0.55)" },
  { value: 0.6, label: "보통 (0.60)" },
  { value: 0.65, label: "좁게 (0.65)" },
  { value: 0.7, label: "아주 좁게 (0.70)" },
];

export function DossierForm({ scopes, dossier }: { scopes: ScopeOption[]; dossier?: DossierDetail }) {
  const [state, action, pending] = useActionState<FormState, FormData>(saveDossier, {});
  const [filter, setFilter] = useState("");
  const [chosen, setChosen] = useState<Set<string>>(new Set(dossier?.criteria.nodes ?? []));
  const criteria = dossier?.criteria;
  const needle = filter.trim().toLowerCase();

  return (
    <form action={action} className="space-y-5">
      {dossier ? <input type="hidden" name="id" value={dossier.id} /> : null}
      <div className="space-y-1.5">
        <label htmlFor="d-title" className="text-sm font-medium">
          제목
        </label>
        <input id="d-title" name="title" required minLength={2} maxLength={120} defaultValue={dossier?.title} className={field} placeholder="예: 온디바이스 AI 칩 경쟁" />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="d-description" className="text-sm font-medium">
          설명 <span className="font-normal text-muted-foreground">(왜 보는지, 무엇을 판단하려는지)</span>
        </label>
        <textarea id="d-description" name="description" rows={2} maxLength={2000} defaultValue={dossier?.description ?? ""} className={field} />
      </div>

      <fieldset className="space-y-4 rounded-md border p-4">
        <legend className="px-1 text-sm font-semibold">어떤 카드를 모을지</legend>
        <p className="text-xs text-muted-foreground">아래 조건 중 하나라도 맞으면 모읍니다. 제외 단어가 제목에 있으면 뺍니다.</p>
        <div className="space-y-1.5">
          <label htmlFor="d-statement" className="text-sm font-medium">
            의미 검색 문장
          </label>
          <textarea id="d-statement" name="statement" rows={2} maxLength={500} defaultValue={criteria?.statement ?? ""} className={field} placeholder="예: 스마트폰·PC에서 생성형 AI를 직접 돌리는 NPU와 칩 경쟁" />
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="d-similarity" className="text-muted-foreground">
              일치 정도
            </label>
            <select id="d-similarity" name="min_similarity" defaultValue={String(criteria?.min_similarity ?? 0.6)} className="h-8 rounded-md border bg-background px-2">
              {SIMILARITY.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="d-keywords" className="text-sm font-medium">
              키워드 <span className="font-normal text-muted-foreground">(쉼표로 구분)</span>
            </label>
            <input id="d-keywords" name="keywords" defaultValue={criteria?.keywords.join(", ")} className={field} placeholder="NPU, 온디바이스 AI" />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="d-companies" className="text-sm font-medium">
              기업 <span className="font-normal text-muted-foreground">(등록된 이름·별칭)</span>
            </label>
            <input id="d-companies" name="companies" defaultValue={criteria?.companies.map((c) => c.label).join(", ")} className={field} placeholder="퀄컴, 미디어텍, Apple" />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <label htmlFor="d-exclude" className="text-sm font-medium">
              제외 단어
            </label>
            <input id="d-exclude" name="exclude" defaultValue={criteria?.exclude.join(", ")} className={field} placeholder="채용, 할인" />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="d-node-filter" className="text-sm font-medium">
            기술·테마 분류 <span className="font-normal text-muted-foreground">(하위 분류 포함, {chosen.size}개 선택)</span>
          </label>
          <input id="d-node-filter" value={filter} onChange={(e) => setFilter(e.target.value)} className={field} placeholder="분류 이름으로 찾기" />
          <div className="max-h-56 overflow-y-auto rounded-md border p-2">
            {scopes.map((scope) => {
              const visible = !needle || scope.label.toLowerCase().includes(needle) || chosen.has(scope.value);
              return (
                <label key={scope.value} className={`flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted ${visible ? "" : "hidden"}`}>
                  <input
                    type="checkbox"
                    name="nodes"
                    value={scope.value}
                    checked={chosen.has(scope.value)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(scope.value);
                      else next.delete(scope.value);
                      setChosen(next);
                    }}
                  />
                  {scope.label}
                </label>
              );
            })}
          </div>
        </div>
      </fieldset>

      {state.error ? (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          {state.error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? "저장 중…" : dossier ? "저장" : "만들기"}
        </Button>
        <Button asChild variant="ghost">
          <Link href={dossier ? `/dossiers/${dossier.id}` : "/dossiers"}>취소</Link>
        </Button>
      </div>
    </form>
  );
}
