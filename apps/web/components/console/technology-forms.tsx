"use client";

import { Check, EyeOff, Link2, Pencil, Plus } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { createTechnology, updateTechnology } from "@/app/console/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TechnologyCandidate, TechnologyOut } from "@/lib/types";

const KINDS = [
  ["technology", "기술"],
  ["standard", "표준"],
  ["regulation", "규제"],
  ["product_family", "제품군"],
] as const;
const STATUSES = [
  ["active", "활성"],
  ["watch", "감시"],
  ["ignored", "무시"],
] as const;

function useAction() {
  const [pending, start] = useTransition();
  const run = (work: () => Promise<{ ok: boolean; error?: string }>, done: string, after?: () => void) =>
    start(async () => {
      const result = await work();
      if (result.ok) {
        toast.success(done);
        after?.();
      } else toast.error(result.error ?? "실패했습니다");
    });
  return { pending, run };
}

const select = "h-8 rounded-md border bg-background px-2 text-sm";

/** Inline editor for one registry row: label, theme, kind, status and aliases. */
export function TechnologyEditor({ tech, themes }: { tech: TechnologyOut; themes: string[] }) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(tech.label);
  const [theme, setTheme] = useState(tech.theme_key ?? "");
  const [kind, setKind] = useState<string>(tech.kind);
  const [status, setStatus] = useState<string>(tech.status);
  const [alias, setAlias] = useState("");
  const { pending, run } = useAction();
  if (!open) {
    return (
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)} aria-label={`${tech.label} 편집`}>
        <Pencil className="size-3.5" />
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 p-2">
      <Input value={label} onChange={(e) => setLabel(e.target.value)} className="h-8 w-40" aria-label="이름" />
      <select value={theme} onChange={(e) => setTheme(e.target.value)} className={select} aria-label="테마">
        <option value="">(테마 없음)</option>
        {themes.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <select value={kind} onChange={(e) => setKind(e.target.value)} className={select} aria-label="종류">
        {KINDS.map(([k, name]) => (
          <option key={k} value={k}>
            {name}
          </option>
        ))}
      </select>
      <select value={status} onChange={(e) => setStatus(e.target.value)} className={select} aria-label="상태">
        {STATUSES.map(([s, name]) => (
          <option key={s} value={s}>
            {name}
          </option>
        ))}
      </select>
      <Input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="별칭 추가(쉼표)" className="h-8 w-44" aria-label="별칭 추가" />
      <Button
        size="sm"
        disabled={pending}
        onClick={() =>
          run(
            () =>
              updateTechnology(tech.key, {
                label,
                theme_key: theme || null,
                kind,
                status,
                add_aliases: alias.split(",").map((a) => a.trim()).filter(Boolean),
              }),
            "저장했습니다. 카드 키를 다시 계산했습니다",
            () => setOpen(false),
          )
        }
      >
        <Check className="size-4" /> 저장
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
        취소
      </Button>
    </div>
  );
}

/** Candidate queue row: add as a technology, fold into an existing key, or ignore. */
export function CandidateActions({ candidate, themes, keys }: { candidate: TechnologyCandidate; themes: string[]; keys: string[] }) {
  const [mode, setMode] = useState<"none" | "add" | "alias">("none");
  const [label, setLabel] = useState(candidate.label);
  const [theme, setTheme] = useState("");
  const [target, setTarget] = useState("");
  const { pending, run } = useAction();
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {mode === "add" ? (
        <>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} className="h-8 w-36" aria-label="이름" />
          <select value={theme} onChange={(e) => setTheme(e.target.value)} className={select} aria-label="테마">
            <option value="">(테마 선택)</option>
            {themes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <Button size="sm" disabled={pending} onClick={() => run(() => createTechnology({ key: candidate.key, label, theme_key: theme || null }), "기술로 추가했습니다")}>
            추가
          </Button>
        </>
      ) : mode === "alias" ? (
        <>
          <Input list="technology-keys" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="기존 기술 키" className="h-8 w-40" aria-label="합칠 기술 키" />
          <datalist id="technology-keys">
            {keys.map((k) => (
              <option key={k} value={k} />
            ))}
          </datalist>
          <Button size="sm" disabled={pending || !target} onClick={() => run(() => updateTechnology(target, { add_aliases: [candidate.key] }), `${target}의 별칭으로 합쳤습니다`)}>
            합치기
          </Button>
        </>
      ) : (
        <>
          <Button size="sm" variant="outline" onClick={() => setMode("add")}>
            <Plus className="size-3.5" /> 기술로
          </Button>
          <Button size="sm" variant="outline" onClick={() => setMode("alias")}>
            <Link2 className="size-3.5" /> 별칭으로
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={pending}
            onClick={() => run(() => createTechnology({ key: candidate.key, label: candidate.label, status: "ignored" }), "무시 목록에 넣었습니다")}
          >
            <EyeOff className="size-3.5" /> 무시
          </Button>
        </>
      )}
    </div>
  );
}
