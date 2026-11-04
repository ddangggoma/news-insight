"use client";

import { Link2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { linkModelAlias } from "@/app/console/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { UnmatchedModel } from "@/lib/types";

/** Link one leaderboard name to a model: the name is kept as the alias, and the model is created
 * when it does not exist. Scores of the same spelling (also once normalized) are linked at once. */
export function LinkModelForm({ model }: { model: UnmatchedModel }) {
  const [name, setName] = useState(model.model_raw);
  const [org, setOrg] = useState(model.org ?? "");
  const [pending, start] = useTransition();
  const submit = () =>
    start(async () => {
      const result = await linkModelAlias(model.model_raw, name.trim(), org.trim());
      if (result.ok) toast.success("연결했습니다. 같은 이름의 점수에 모델을 채웠습니다");
      else toast.error(result.error ?? "실패했습니다");
    });
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="h-8 w-56" aria-label={`${model.model_raw} 모델 이름`} />
      <Input value={org} onChange={(e) => setOrg(e.target.value)} maxLength={80} placeholder="제작사" className="h-8 w-32" aria-label={`${model.model_raw} 제작사`} />
      <Button type="submit" size="sm" disabled={pending || !name.trim()}>
        <Link2 className="size-3.5" /> 연결
      </Button>
    </form>
  );
}
