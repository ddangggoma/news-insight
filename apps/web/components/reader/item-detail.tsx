import { ExternalLink } from "lucide-react";
import Link from "next/link";
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
            <Link href={`/items/${row.id}`} className="block rounded-lg border px-3 py-2 hover:border-primary/50">
              <span className="block text-sm leading-snug font-medium">{row.title_ko ?? row.title}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <TrackBadge track={row.track} />
                {row.source_name} · {formatRelative(row.first_seen_at)}
                {row.ref ? <span className="font-mono">{row.ref}</span> : null}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ItemDetailView({ detail }: { detail: ReaderItemDetail }) {
  const { item } = detail;
  const showOriginal = item.title_ko !== null && item.title_ko.trim() !== item.title.trim();
  return (
    <article className="space-y-5">
      <div className="flex flex-wrap items-center gap-1.5">
        <FieldTag field={item.field} />
        <SignalTag signal={item.signal_type} />
        <ImpactBadge impact={item.impact} />
      </div>
      <header className="space-y-1.5">
        <h2 className="text-xl leading-snug font-bold text-balance">{item.title_ko ?? item.title}</h2>
        {showOriginal ? <p className="text-sm text-muted-foreground">원제: {item.title}</p> : null}
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <TrackBadge track={item.track} />
          {item.source_name} · {REGION_LABEL[item.region]} · <time dateTime={item.first_seen_at}>{formatDateTime(item.first_seen_at)}</time>
        </p>
      </header>
      {item.summary_ko.length ? (
        <ul className="list-disc space-y-1.5 pl-5 text-base leading-relaxed">
          {item.summary_ko.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
        {item.themes.length ? (
          <>
            <dt className="text-muted-foreground">테마</dt>
            <dd>{item.themes.map((theme) => THEME_LABEL[theme] ?? theme).join(", ")}</dd>
          </>
        ) : null}
        {item.scope ? (
          <>
            <dt className="text-muted-foreground">범위</dt>
            <dd>{SCOPE_LABEL[item.scope] ?? item.scope}</dd>
          </>
        ) : null}
        {item.relevance !== null ? (
          <>
            <dt className="text-muted-foreground">관련도</dt>
            <dd className="tabular-nums">{item.relevance} / 100</dd>
          </>
        ) : null}
        {item.companies?.length ? (
          <>
            <dt className="text-muted-foreground">기업</dt>
            <dd>
              <CompanyChips companies={item.companies} max={8} />
            </dd>
          </>
        ) : null}
        {item.keywords.length ? (
          <>
            <dt className="text-muted-foreground">키워드</dt>
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
      <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
        원문 보기 <ExternalLink className="size-3.5" aria-hidden />
      </a>
      <Linked title={`같은 이슈의 다른 보도 ${detail.story_items.length}건`} rows={detail.story_items} />
      <Linked title="교차 신호 (같은 논문·저장소를 가리키는 항목)" rows={detail.signals} />
      <Linked title="같은 분야 최근 기사" rows={detail.same_field} />
      <ItemTeamPanel itemId={item.id} />
    </article>
  );
}
