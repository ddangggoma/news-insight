import Link from "next/link";

import type { Insights } from "@/lib/reader-types";
import { type ReaderFilters, setHref } from "@/lib/reader-filters";
import { FIELD_LABEL, IMPACT_LABEL, SIGNAL_LABEL } from "@/lib/taxonomy";
import { formatNumber } from "@/lib/format";

const IMPACT_COLOR: Record<string, string> = {
  opportunity: "bg-impact-opportunity",
  risk: "bg-impact-risk",
  watch: "bg-impact-watch",
};

function Share({ rows, labels, total }: { rows: { key: string; count: number }[]; labels: Record<string, string>; total: number }) {
  return (
    <ul className="space-y-2">
      {rows.slice(0, 7).map((row) => {
        const share = total ? Math.round((row.count / total) * 100) : 0;
        return (
          <li key={row.key} className="grid grid-cols-[96px_minmax(0,1fr)_40px] items-center gap-2 text-sm text-ink-2">
            <span className="truncate" title={labels[row.key]}>
              {(labels[row.key] ?? row.key).split(" · ")[0]}
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-muted">
              <span className="block h-full rounded-full bg-primary" style={{ width: `${share}%` }} />
            </span>
            <span className="text-right text-xs text-muted-foreground tabular-nums">{share}%</span>
          </li>
        );
      })}
    </ul>
  );
}

export function InsightPanel({ insights, filters }: { insights: Insights; filters: ReaderFilters }) {
  const impactTotal = insights.impacts.reduce((sum, row) => sum + row.count, 0);
  return (
    <div className="space-y-7">
      <section>
        <h2 className="mb-1 flex items-baseline justify-between text-sm font-bold">
          많이 언급된 키워드 <span className="text-xs font-normal text-muted-foreground">직전 같은 기간 대비</span>
        </h2>
        {insights.keywords.length ? (
          <ol className="divide-y">
            {insights.keywords.map((keyword, index) => (
              <li key={keyword.key} className="flex items-center gap-2 py-2 text-sm">
                <span className="w-4 text-xs text-muted-foreground tabular-nums">{index + 1}</span>
                <Link href={setHref(filters, "q", keyword.label)} className="min-w-0 flex-1 truncate hover:underline">
                  {keyword.label}
                </Link>
                <span className="text-xs text-muted-foreground tabular-nums">{keyword.count}건</span>
                <span className="w-16 shrink-0 text-right text-xs font-semibold whitespace-nowrap tabular-nums">
                  {keyword.is_new ? (
                    <span className="rounded bg-chart-4/20 px-1.5 text-foreground">신규</span>
                  ) : keyword.change === null ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <span className={keyword.change >= 0 ? "text-impact-opportunity" : "text-impact-risk"}>
                      {keyword.change >= 0 ? "▲" : "▼"}
                      {Math.round(Math.abs(keyword.change))}%
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">2건 이상 언급된 키워드가 아직 없습니다.</p>
        )}
      </section>
      <section>
        <h2 className="mb-2 text-sm font-bold">분야 점유율</h2>
        <Share rows={insights.fields} labels={FIELD_LABEL} total={insights.total} />
      </section>
      <section>
        <h2 className="mb-2 text-sm font-bold">신호 유형</h2>
        <Share rows={insights.signal_types} labels={SIGNAL_LABEL} total={insights.total} />
      </section>
      <section>
        <h2 className="mb-2 text-sm font-bold">영향 분포</h2>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
          {insights.impacts.map((row) => (
            <span
              key={row.key}
              className={IMPACT_COLOR[row.key]}
              style={{ width: `${impactTotal ? (row.count / impactTotal) * 100 : 0}%` }}
            />
          ))}
        </div>
        <p className="mt-2 flex flex-wrap gap-3 text-xs text-ink-2">
          {insights.impacts.map((row) => (
            <span key={row.key}>
              {IMPACT_LABEL[row.key] ?? row.key} <b className="tabular-nums">{formatNumber(row.count)}</b>
            </span>
          ))}
        </p>
      </section>
      {insights.related_keywords.length ? (
        <section>
          <h2 className="mb-2 text-sm font-bold">함께 언급된 키워드</h2>
          <div className="flex flex-wrap gap-1.5">
            {insights.related_keywords.map((keyword) => (
              <Link
                key={keyword}
                href={setHref(filters, "q", keyword)}
                className="rounded-md bg-muted px-2 py-0.5 text-xs text-ink-2 hover:bg-primary/10 hover:text-primary"
              >
                {keyword}
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
