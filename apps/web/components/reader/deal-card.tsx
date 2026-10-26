import { ExternalLink } from "lucide-react";

import { AppLink as Link } from "@/components/app-link";
import { DEAL_KIND_LABEL, DEAL_SERIES_COLOR, type Deal, dealSeries, formatOriginal, formatUsd } from "@/lib/deal-types";
import { formatDay } from "@/lib/format";
import { cn } from "@/lib/utils";

function Party({ name, companyKey, href }: { name: string; companyKey: string | null; href: (company: string) => string }) {
  return companyKey ? (
    <Link href={href(companyKey)} className="hover:text-primary hover:underline">
      {name}
    </Link>
  ) : (
    <span>{name}</span>
  );
}

/** One deal: kind and date, who with whom, the size, what happened and the card it came from. */
export function DealCard({ deal, companyHref }: { deal: Deal; companyHref: (company: string) => string }) {
  const day = deal.occurred_on ?? deal.announced_on;
  const original = formatOriginal(deal.amount, deal.currency);
  return (
    <article className="flex min-w-0 flex-col rounded-2xl border bg-card p-4 shadow-xs [content-visibility:auto] [contain-intrinsic-size:auto_220px]">
      <div className="flex items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 font-semibold text-ink-2">
          <span aria-hidden className="size-2 rounded-full" style={{ background: DEAL_SERIES_COLOR[dealSeries(deal.kind)] }} />
          {DEAL_KIND_LABEL[deal.kind]}
        </span>
        {deal.stage ? <span className="truncate rounded-full border px-2 py-0.5 text-ink-2">{deal.stage}</span> : null}
        <time
          className="ml-auto shrink-0 text-muted-foreground tabular-nums"
          dateTime={day ?? undefined}
          title={deal.announced_on ? "발표일" : "발표일이 없어 근거 기사 날짜"}
        >
          {day ? formatDay(day) : ""}
        </time>
      </div>

      <h3 className="mt-3 text-[15px] leading-snug font-semibold">
        <Party name={deal.actor} companyKey={deal.actor_key} href={companyHref} />
        {deal.counterparty ? (
          <>
            <span aria-hidden className="mx-1.5 font-normal text-muted-foreground">
              →
            </span>
            <span className="sr-only">상대: </span>
            <Party name={deal.counterparty} companyKey={deal.counterparty_key} href={companyHref} />
          </>
        ) : null}
      </h3>

      {deal.amount_usd ? (
        <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2">
          <span className={cn("text-lg font-bold tracking-tight tabular-nums", deal.outlier && "text-muted-foreground line-through decoration-1")}>{formatUsd(deal.amount_usd)}</span>
          {original ? <span className="text-xs text-muted-foreground tabular-nums">{original}</span> : null}
          {deal.outlier ? (
            <span title="500억 달러 이상은 기업가치 등을 금액으로 잘못 읽은 경우가 많아 합계에서 뺍니다." className="rounded-full bg-impact-risk/12 px-1.5 py-px text-[11px] font-semibold text-impact-risk">
              확인 필요, 합계 제외
            </span>
          ) : null}
        </p>
      ) : (
        <p className="mt-1.5 text-xs text-muted-foreground">금액 비공개</p>
      )}

      <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-ink-2">{deal.summary}</p>

      <div className="flex-1" />
      <footer className="mt-3 border-t pt-2.5 text-xs text-muted-foreground">
        <Link href={`/items/${deal.item_id}`} scroll={false} className="line-clamp-1 font-medium text-foreground hover:text-primary hover:underline">
          {deal.title}
        </Link>
        <div className="mt-1 flex items-center gap-2">
          <span className="truncate">{deal.source}</span>
          {deal.reports > 1 ? <span className="shrink-0 rounded-full bg-muted px-1.5 py-px text-ink-2">보도 {deal.reports}건</span> : null}
          <a href={deal.url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex shrink-0 items-center gap-1 hover:text-primary">
            원문
            <ExternalLink aria-hidden className="size-3" />
          </a>
        </div>
      </footer>
    </article>
  );
}
