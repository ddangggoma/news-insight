"use client";

import { createContext, type ReactNode, useContext, useState, useTransition } from "react";
import { toast } from "sonner";

import { type BulkAction, bulkSources } from "@/app/console/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Select sources on the current page and pause, resume or retire them together (2026-10-08).
type Selection = { keys: Set<string>; toggle: (key: string) => void; set: (keys: string[]) => void };
const SelectionContext = createContext<Selection | null>(null);

function useSelection(): Selection {
  const value = useContext(SelectionContext);
  if (!value) throw new Error("BulkSelection is missing");
  return value;
}

export function BulkSelection({ children }: { children: ReactNode }) {
  const [keys, setKeys] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return <SelectionContext.Provider value={{ keys, toggle, set: (list) => setKeys(new Set(list)) }}>{children}</SelectionContext.Provider>;
}

export function BulkCheckbox({ sourceKey }: { sourceKey: string }) {
  const { keys, toggle } = useSelection();
  return <input type="checkbox" aria-label={`${sourceKey} 선택`} checked={keys.has(sourceKey)} onChange={() => toggle(sourceKey)} className="size-4 accent-primary" />;
}

const ACTION_LABEL: Record<BulkAction, string> = { pause: "일시정지", resume: "재개", retire: "수집 중단(retire)" };

export function BulkBar({ pageKeys }: { pageKeys: string[] }) {
  const { keys, set } = useSelection();
  const [action, setAction] = useState<BulkAction>("pause");
  const [reason, setReason] = useState("");
  const [pending, start] = useTransition();
  const all = pageKeys.length > 0 && pageKeys.every((key) => keys.has(key));
  const needsReason = action !== "resume";
  const submit = () =>
    start(async () => {
      const result = await bulkSources([...keys], action, reason.trim());
      if (!result.ok) {
        toast.error(result.error ?? "실패했습니다");
        return;
      }
      if (result.done.length) toast.success(`${ACTION_LABEL[action]} ${result.done.length}개 완료`);
      if (result.failed.length) toast.error(`${result.failed.length}개 실패: ${result.failed.slice(0, 3).map((f) => `${f.key} (${f.error})`).join(", ")}`);
      set([]);
      setReason("");
    });
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2 text-sm">
      <label className="flex items-center gap-2 px-1">
        <input type="checkbox" aria-label="이 페이지 전체 선택" checked={all} onChange={() => set(all ? [] : pageKeys)} className="size-4 accent-primary" />
        <span className="text-muted-foreground">{keys.size ? `${keys.size}개 선택` : "이 페이지 전체"}</span>
      </label>
      <select aria-label="일괄 작업" value={action} onChange={(event) => setAction(event.target.value as BulkAction)} className="h-8 rounded-md border bg-background px-2">
        {(Object.keys(ACTION_LABEL) as BulkAction[]).map((value) => (
          <option key={value} value={value}>
            {ACTION_LABEL[value]}
          </option>
        ))}
      </select>
      {needsReason ? <Input aria-label="사유" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="사유 (필수)" className="h-8 w-56" /> : null}
      <Button
        size="sm"
        variant={action === "retire" ? "destructive" : "default"}
        disabled={pending || keys.size === 0 || (needsReason && !reason.trim())}
        onClick={() => {
          if (action === "retire" && !window.confirm(`${keys.size}개 소스의 수집을 중단합니다. 카탈로그에 남아 있으면 다음 seed 때 다시 살아납니다. 계속할까요?`)) return;
          submit();
        }}
      >
        적용
      </Button>
    </div>
  );
}
