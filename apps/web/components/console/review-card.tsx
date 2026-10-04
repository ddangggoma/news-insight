"use client";

import { Check, CircleHelp, ExternalLink, X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { submitReview } from "@/app/console/actions";
import { TrackBadge } from "@/components/console/badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CATEGORY_LABEL } from "@/lib/format";
import type { ReviewItem, Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

const OPTIONS: { verdict: Verdict; label: string; icon: typeof Check; active: string }[] = [
  { verdict: "relevant", label: "관련", icon: Check, active: "bg-emerald-600 text-white hover:bg-emerald-600/90" },
  { verdict: "irrelevant", label: "무관", icon: X, active: "bg-destructive text-white hover:bg-destructive/90" },
  { verdict: "unsure", label: "애매", icon: CircleHelp, active: "bg-amber-500 text-white hover:bg-amber-500/90" },
];

export function ReviewCard({ view, seed, index }: { view: ReviewItem; seed: string; index: number }) {
  const { item, card } = view;
  const [verdict, setVerdict] = useState<Verdict | null>(view.review?.verdict ?? null);
  const [note, setNote] = useState(view.review?.note ?? "");
  const [pending, startTransition] = useTransition();

  function save(next: Verdict) {
    const previous = verdict;
    setVerdict(next);
    startTransition(async () => {
      try {
        await submitReview(item.id, next, note, seed);
      } catch (error) {
        setVerdict(previous);
        toast.error(error instanceof Error ? error.message : "저장하지 못했습니다");
      }
    });
  }

  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-4 transition-colors",
        verdict === "relevant" && "border-emerald-500/50",
        verdict === "irrelevant" && "border-destructive/50",
        verdict === "unsure" && "border-amber-500/50",
      )}
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono tabular-nums">#{index + 1}</span>
        <TrackBadge track={item.track} />
        <span className="truncate">{CATEGORY_LABEL[item.category] ?? item.category}</span>
        <span className="ml-auto truncate">{item.source_name}</span>
      </div>
      <div className="space-y-1">
        <h3 className="leading-snug font-semibold text-balance">{card?.title_ko ?? item.title}</h3>
        {card?.title_ko && card.title_ko !== item.title ? (
          <p className="line-clamp-2 text-xs text-muted-foreground">{item.title}</p>
        ) : null}
      </div>
      {card && card.summary_ko.length > 0 ? (
        <p className="line-clamp-3 text-sm text-muted-foreground">{card.summary_ko.join(" ")}</p>
      ) : null}
      {card && card.keywords.length > 0 ? (
        <p className="text-xs text-muted-foreground">{card.keywords.map((k) => `#${k}`).join(" ")}</p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        {OPTIONS.map((option) => (
          <Button
            key={option.verdict}
            size="sm"
            variant={verdict === option.verdict ? "default" : "outline"}
            className={cn(verdict === option.verdict && option.active)}
            disabled={pending}
            aria-pressed={verdict === option.verdict}
            onClick={() => save(option.verdict)}
          >
            <option.icon /> {option.label}
          </Button>
        ))}
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          원문 <ExternalLink className="size-3" />
        </a>
      </div>
      <Input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        onBlur={() => verdict && note !== (view.review?.note ?? "") && save(verdict)}
        placeholder="메모 (선택, 입력 후 다른 곳을 누르면 저장)"
        className="h-8 text-xs"
        maxLength={500}
      />
    </article>
  );
}
