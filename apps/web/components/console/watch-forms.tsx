"use client";

import { Plus, X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { addWatch, removeWatch } from "@/app/console/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { THEME_LABEL } from "@/lib/taxonomy";
import type { WatchItem, WatchPage } from "@/lib/types";

const KIND_LABEL: Record<WatchItem["kind"], string> = { company: "기업", theme: "테마", keyword: "기술 키워드" };

function useRun() {
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

export function WatchAdd({ companies }: { companies: WatchPage["companies"] }) {
  const { pending, run } = useRun();
  const [kind, setKind] = useState<WatchItem["kind"]>("company");
  const [value, setValue] = useState("");
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim()) run(() => addWatch(kind, value), "관심 항목에 추가했습니다", () => setValue(""));
      }}
    >
      <select
        id="watch-kind"
        aria-label="종류"
        value={kind}
        onChange={(event) => {
          setKind(event.target.value as WatchItem["kind"]);
          setValue("");
        }}
        className="h-9 rounded-md border bg-background px-2 text-sm"
      >
        {(Object.keys(KIND_LABEL) as WatchItem["kind"][]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABEL[k]}
          </option>
        ))}
      </select>
      {kind === "company" ? (
        <select id="watch-company" aria-label="기업" value={value} onChange={(event) => setValue(event.target.value)} className="h-9 min-w-56 rounded-md border bg-background px-2 text-sm">
          <option value="">기업 선택</option>
          {companies.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      ) : kind === "theme" ? (
        <select id="watch-theme" aria-label="테마" value={value} onChange={(event) => setValue(event.target.value)} className="h-9 min-w-56 rounded-md border bg-background px-2 text-sm">
          <option value="">테마 선택</option>
          {Object.entries(THEME_LABEL).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      ) : (
        <Input id="watch-keyword" aria-label="기술 키워드" value={value} onChange={(event) => setValue(event.target.value)} placeholder="예: 온디바이스 AI, HBM4" className="h-9 w-56" />
      )}
      <Button type="submit" size="sm" disabled={pending || !value.trim()}>
        <Plus className="size-4" aria-hidden /> 추가
      </Button>
    </form>
  );
}

export function WatchRemove({ item }: { item: WatchItem }) {
  const { pending, run } = useRun();
  return (
    <Button variant="ghost" size="sm" disabled={pending} aria-label={`${item.label} 삭제`} onClick={() => run(() => removeWatch(item.id), "삭제했습니다")}>
      <X className="size-4" aria-hidden />
    </Button>
  );
}

export function WatchSuggest({ suggestion }: { suggestion: WatchPage["suggestions"][number] }) {
  const { pending, run } = useRun();
  return (
    <Button variant="outline" size="sm" disabled={pending} onClick={() => run(() => addWatch(suggestion.kind, suggestion.key), "관심 항목에 추가했습니다")}>
      <Plus className="size-3.5" aria-hidden /> {suggestion.kind === "theme" ? THEME_LABEL[suggestion.key] ?? suggestion.label : suggestion.label}
      <span className="text-xs text-muted-foreground tabular-nums">{suggestion.count}</span>
    </Button>
  );
}

export { KIND_LABEL };
