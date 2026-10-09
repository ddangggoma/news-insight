"use client";

import { ExternalLink, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { askQuestion } from "@/app/(reader)/ask/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { type AskResult, type ScopeOption, citationParts } from "@/lib/ask-types";
import { formatDateTime } from "@/lib/format";

const PERIODS = [
  { days: 7, label: "최근 1주" },
  { days: 30, label: "최근 1개월" },
  { days: 90, label: "최근 3개월" },
  { days: 180, label: "최근 6개월" },
  { days: 365, label: "최근 1년" },
];
const HISTORY_KEY = "ask-history";
const EXAMPLES = ["온디바이스 AI 경쟁 동향은?", "최근 배터리 안전 규제 변화는?", "AI 에이전트 보안 이슈는 무엇이 있나?"];

function readHistory(): string[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, 10) : [];
  } catch {
    return [];
  }
}

function saveHistory(items: string[]) {
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 10)));
  } catch {
    // private window or blocked storage: history is a convenience only
  }
}

const selectClass = "h-9 rounded-md border bg-background px-2 text-sm";

export function AskPanel({ scopes }: { scopes: ScopeOption[] }) {
  const [question, setQuestion] = useState("");
  const [days, setDays] = useState(30);
  const [node, setNode] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [pending, startTransition] = useTransition();

  useEffect(() => setHistory(readHistory()), []);

  function submit(text: string) {
    const asked = text.trim();
    if (asked.length < 2 || pending) return;
    setQuestion(asked);
    setError(null);
    startTransition(async () => {
      const outcome = await askQuestion({ question: asked, days, node: node || null });
      if (outcome.ok) {
        setResult(outcome.result);
        const next = [asked, ...history.filter((h) => h !== asked)];
        setHistory(next.slice(0, 10));
        saveHistory(next);
      } else {
        setError(outcome.error);
      }
    });
  }

  return (
    <div className="space-y-4">
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          submit(question);
        }}
      >
        <label htmlFor="ask-question" className="sr-only">
          질문
        </label>
        <textarea
          id="ask-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit(question);
          }}
          maxLength={500}
          rows={3}
          placeholder="예: 최근 한 달 온디바이스 AI 칩 경쟁에서 눈에 띄는 움직임은?"
          className="w-full resize-y rounded-md border bg-background p-3 text-sm"
        />
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="기간" value={days} onChange={(e) => setDays(Number(e.target.value))} className={selectClass}>
            {PERIODS.map((p) => (
              <option key={p.days} value={p.days}>
                {p.label}
              </option>
            ))}
          </select>
          <select aria-label="범위" value={node} onChange={(e) => setNode(e.target.value)} className={`${selectClass} max-w-[16rem]`}>
            <option value="">전체 분야</option>
            {scopes.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <Button type="submit" size="sm" disabled={pending || question.trim().length < 2} className="ml-auto">
            {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
            {pending ? "답하는 중…" : "질문"}
          </Button>
        </div>
      </form>

      {!result && !pending && !error ? (
        <div className="flex flex-wrap gap-2">
          {(history.length ? history : EXAMPLES).map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => submit(h)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
            >
              {h}
            </button>
          ))}
        </div>
      ) : null}

      {pending ? (
        <p role="status" className="text-sm text-muted-foreground">
          근거 기사를 찾고 로컬 모델이 답을 쓰는 중입니다. 카드 작업과 모델을 함께 쓰므로 1~2분 걸릴 수 있습니다.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          {error}
        </p>
      ) : null}

      {result && !pending ? <Answer result={result} /> : null}
    </div>
  );
}

function Answer({ result }: { result: AskResult }) {
  const parts = citationParts(result.answer, result.evidence.length);
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-2 pt-6">
          <p className="text-xs text-muted-foreground">
            {result.question} · 근거 {result.evidence.length}건 · {(result.took_ms / 1000).toFixed(1)}초
          </p>
          <div data-testid="ask-answer" className="text-sm leading-relaxed whitespace-pre-wrap">
            {parts.map((part, index) =>
              typeof part === "number" ? (
                <a
                  key={index}
                  href={`#evidence-${part}`}
                  className="mx-0.5 rounded bg-primary/10 px-1 text-xs font-medium text-primary align-super"
                >
                  {part}
                </a>
              ) : (
                <span key={index}>{part}</span>
              ),
            )}
          </div>
        </CardContent>
      </Card>
      {result.evidence.length ? (
        <section aria-labelledby="evidence-heading" className="space-y-2">
          <h2 id="evidence-heading" className="text-sm font-semibold">
            근거 기사
          </h2>
          <ol className="space-y-1.5">
            {result.evidence.map((e) => (
              <li
                key={e.n}
                id={`evidence-${e.n}`}
                className={`flex gap-2 rounded-md border p-2 text-sm target:ring-2 target:ring-primary ${result.cited.includes(e.n) ? "" : "opacity-70"}`}
              >
                <span className="w-6 shrink-0 text-right font-medium text-primary">[{e.n}]</span>
                <div className="min-w-0 flex-1">
                  <Link href={`/items/${e.item_id}`} className="line-clamp-2 hover:underline">
                    {e.title}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {e.source} · {formatDateTime(e.first_seen_at)} · 유사도 {e.similarity.toFixed(2)}
                    {result.cited.includes(e.n) ? "" : " · 답에 인용 안 됨"}
                  </p>
                </div>
                <a href={e.url} target="_blank" rel="noreferrer noopener" aria-label="원문 열기" className="shrink-0 text-muted-foreground hover:text-foreground">
                  <ExternalLink className="size-4" aria-hidden />
                </a>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
