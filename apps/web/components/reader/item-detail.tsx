import { ExternalLink } from "lucide-react";
import { AppLink as Link } from "@/components/app-link";
import { notFound } from "next/navigation";

import { TrackBadge } from "@/components/console/badges";
import { ItemTeamPanel } from "@/components/reader/item-team";
import { CompanyChips, SignalTag, FieldTag, ImpactBadge } from "@/components/reader/labels";
import { ApiError } from "@/lib/api";
import { formatDateTime, formatRelative, REGION_LABEL } from "@/lib/format";
import { readerGet } from "@/lib/reader-api";
import type { LinkedItem, ReaderItemDetail } from "@/lib/reader-types";
import { SCOPE_LABEL, THEME_LABEL } from "@/lib/taxonomy";

export async function loadItem(id: string): Promise<ReaderItemDetail> {
  if (!/^\d+$/.test(id)) notFound();
  try {
    return await readerGet<ReaderItemDetail>(`/items/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

function Linked({ title, rows }: { title: string; rows: LinkedItem[] }) {
  if (!rows.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
      <ul className="space-y-1.5">
        {rows.map((row) => (
          <li key={`${row.id}-${row.ref ?? ""}`}>
            <Link href={`/items/${row.id}`} className="block rounded-lg border bg-card px-3 py-2.5 transition-colors hover:border-primary/50 hover:bg-primary/[0.03]">
              <span className="block text-sm leading-snug font-medium">{row.title_ko ?? row.title}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <TrackBadge track={row.track} />
                {row.source_name} · {formatRelative(row.occurred_at)}
                {row.ref ? <span className="font-mono">{row.ref}</span> : null}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

// collected more than a day after its own date: a backfill or a late feed, worth saying so
function lateBy(item: ReaderItemDetail["item"]): boolean {
  return Date.parse(item.first_seen_at) - Date.parse(item.occurred_at) > 86_400_000;
}

export function ItemDetailView({ detail }: { detail: ReaderItemDetail }) {
  const { item } = detail;
  const showOriginal = item.title_ko !== null && item.title_ko.trim() !== item.title.trim();
  return (
    // two columns once the view itself is wide (the dialog, a wide page): classification beside the text
    <article className="@container">
      <div className="grid gap-x-8 gap-y-5 @3xl:grid-cols-[minmax(0,1fr)_17rem] @3xl:grid-rows-[auto_auto_1fr]">
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <FieldTag field={item.field} />
            <SignalTag signal={item.signal_type} />
            <ImpactBadge impact={item.impact} />
          </div>
          <h2 className="text-xl leading-snug font-bold tracking-tight md:text-2xl">{item.title_ko ?? item.title}</h2>
          {showOriginal ? <p className="text-sm text-muted-foreground">원제: {item.title}</p> : null}
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <TrackBadge track={item.track} />
            <span>{item.source_name}</span>
            <span aria-hidden>·</span>
            <span>{REGION_LABEL[item.region]}</span>
            <span aria-hidden>·</span>
            <time dateTime={item.occurred_at} className="tabular-nums">{formatDateTime(item.occurred_at)}</time>
            {lateBy(item) ? <span title="기사 날짜보다 늦게 수집됨">(수집 {formatDateTime(item.first_seen_at)})</span> : null}
          </p>
        </header>

        <section aria-label="요약" className="space-y-4">
          {item.summary_ko.length ? (
            <ul className="list-disc space-y-2 pl-5 text-base leading-relaxed marker:text-primary/60">
              {item.summary_ko.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm font-medium text-primary transition-colors hover:border-primary/50 hover:bg-primary/5 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            원문 보기 <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </section>

        <aside aria-label="분류" className="rounded-xl border bg-muted/30 p-4 @3xl:col-start-2 @3xl:row-span-3 @3xl:row-start-1 @3xl:self-start">
          <h3 className="mb-3 text-sm font-semibold text-ink-2">분류</h3>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm @3xl:grid-cols-1 @3xl:gap-y-0.5">
            {item.themes.length ? (
              <>
                <dt className="text-muted-foreground @3xl:text-xs">테마</dt>
                <dd className="@3xl:mb-2.5">{item.themes.map((theme) => THEME_LABEL[theme] ?? theme).join(", ")}</dd>
              </>
            ) : null}
            {item.scope ? (
              <>
                <dt className="text-muted-foreground @3xl:text-xs">범위</dt>
                <dd className="@3xl:mb-2.5">{SCOPE_LABEL[item.scope] ?? item.scope}</dd>
              </>
            ) : null}
            {item.relevance !== null ? (
              <>
                <dt className="text-muted-foreground @3xl:text-xs">관련도</dt>
                <dd className="flex items-center gap-2 @3xl:mb-2.5">
                  <span className="tabular-nums">{item.relevance} / 100</span>
                  <span aria-hidden className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                    <span className="block h-full rounded-full bg-primary/70" style={{ width: `${item.relevance}%` }} />
                  </span>
                </dd>
              </>
            ) : null}
            {item.companies?.length ? (
              <>
                <dt className="text-muted-foreground @3xl:text-xs">기업</dt>
                <dd className="@3xl:mb-2.5">
                  <CompanyChips companies={item.companies} max={8} />
                </dd>
              </>
            ) : null}
            {item.keywords.length ? (
              <>
                <dt className="text-muted-foreground @3xl:text-xs">키워드</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {item.keywords.map((keyword) => (
                    <Link key={keyword} href={`/?q=${encodeURIComponent(keyword)}`} className="rounded bg-muted px-1.5 text-xs text-ink-2 hover:text-primary">
                      #{keyword}
                    </Link>
                  ))}
                </dd>
              </>
            ) : null}
          </dl>
        </aside>

        <div className="min-w-0 space-y-6">
          <Linked title={`같은 이슈의 다른 보도 ${detail.story_items.length}건`} rows={detail.story_items} />
          <Linked title="교차 신호 (같은 논문·저장소를 가리키는 항목)" rows={detail.signals} />
          <Linked title="같은 분야 최근 기사" rows={detail.same_field} />
          <ItemTeamPanel itemId={item.id} />
        </div>
      </div>
    </article>
  );
}
