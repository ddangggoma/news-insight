"use client";

import { Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const storageKey = (date: string) => `reader:digest-dismissed:${date}`;

/** Latest digest headline; closing it hides that day's digest in this browser only. */
export function DigestBanner({ date, headline, insights }: { date: string; headline: string; insights: string[] }) {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(storageKey(date))) setOpen(false);
    } catch {
      // storage unavailable: keep the banner
    }
  }, [date]);
  if (!open) return null;
  const close = () => {
    setOpen(false);
    try {
      window.localStorage.setItem(storageKey(date), "1");
    } catch {
      // ignore
    }
  };
  return (
    <section aria-label="오늘의 다이제스트" className="relative rounded-xl border bg-primary/5 px-4 py-3 pr-10">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
        <Sparkles className="size-3.5" aria-hidden /> {date} 다이제스트
      </p>
      <h2 className="mt-1 text-base leading-snug font-semibold">
        <Link href={`/briefings/${date}`} className="hover:underline">
          {headline}
        </Link>
      </h2>
      {insights.length ? (
        <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
          {insights.slice(0, 3).map((title) => (
            <li key={title} className="before:mr-1.5 before:text-primary before:content-['•']">
              {title}
            </li>
          ))}
        </ul>
      ) : null}
      <button type="button" onClick={close} aria-label="다이제스트 닫기" className="absolute top-2.5 right-2.5 rounded p-1 text-muted-foreground hover:bg-muted">
        <X className="size-4" />
      </button>
    </section>
  );
}
