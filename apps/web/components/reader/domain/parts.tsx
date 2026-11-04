import type { ReactNode } from "react";

import { AppLink as Link } from "@/components/app-link";
import { formatDay, formatNumber } from "@/lib/format";
import {
  DOMAIN_META,
  DOMAIN_TABS,
  type Doc,
  type DomainInsight,
  type DomainKind,
  type DomainState,
  type DomainView,
  type Heatmap,
  type Option,
  PERIODS,
  changeText,
  changeTone,
  domainHref,
  heatLevel,
  shortDay,
  spanLabel,
  tabHref,
} from "@/lib/domain-types";
import { cn } from "@/lib/utils";

// Shared parts of the 연구·특허 pages. No client state: every choice is a link, so the page
// stays a server component and a choice survives a reload or a shared address.

const TONE = {
  up: "text-impact-opportunity",
  down: "text-impact-risk",
  new: "text-primary",
  flat: "text-muted-foreground",
} as const;

/** ▲25% / ▼10% / 새로 in the impact colours. */
export function ChangeBadge({ change, count, previous, className }: { change: number | null; count: number; previous: number; className?: string }) {
  return <span className={cn("font-semibold whitespace-nowrap tabular-nums", TONE[changeTone(change, count, previous)], className)}>{changeText(change, count, previous)}</span>;
}

const RELATION_LABEL: Record<string, string> = { self: "자사", competitor: "경쟁사" };

/** A watched company (relation self or competitor in the registry). */
export function WatchedBadge({ relation }: { relation: string | null }) {
  const detail = relation ? RELATION_LABEL[relation] : undefined;
  return (
    <span title={`관심 기업${detail ? ` (${detail})` : ""}`} className="shrink-0 rounded-full bg-primary/12 px-1.5 py-px text-[11px] font-semibold whitespace-nowrap text-primary">
      관심{detail ? `·${detail}` : ""}
    </span>
  );
}

const segment = (active: boolean) =>
  cn(
    "rounded px-3 py-1 whitespace-nowrap focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
    active ? "bg-primary font-semibold text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
  );

export function DomainTabs({ domain, state }: { domain: DomainKind; state: DomainState }) {
  return (
    <nav aria-label={`${DOMAIN_META[domain].title} 보기`} className="flex gap-1 overflow-x-auto border-b">
      {DOMAIN_TABS.map((tab) => (
        <Link
          key={tab.key}
          href={tabHref(domain, state, tab.key)}
          aria-current={state.tab === tab.key ? "page" : undefined}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            state.tab === tab.key ? "border-primary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

/** 1주 / 1개월 / 분기: the window length (rolling, ending yesterday). */
export function PeriodSelect({ domain, state }: { domain: DomainKind; state: DomainState }) {
  return (
    <nav aria-label="기간" className="flex rounded-md border p-0.5 text-sm">
      {PERIODS.map((p) => (
        <Link key={p.key} href={domainHref(domain, state, { period: p.key, page: 1 })} aria-current={state.period === p.key ? "true" : undefined} className={segment(state.period === p.key)}>
          {p.label}
        </Link>
      ))}
    </nav>
  );
}

/** Links that look like a segmented control, the current one marked. */
export function Segments({ label, items }: { label: string; items: { key: string; label: string; href: string; active: boolean }[] }) {
  return (
    <nav aria-label={label} className="inline-flex rounded-md border p-0.5 text-sm">
      {items.map((item) => (
        <Link key={item.key} href={item.href} scroll={false} aria-current={item.active ? "true" : undefined} className={segment(item.active)}>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

export interface Chip {
  key: string;
  label: string;
  href: string;
  active: boolean;
  count?: number;
}

/** Field (or filter) chips: links, the chosen one marked with aria-current. */
export function ChipRow({ label, chips }: { label: string; chips: Chip[] }) {
  return (
    <nav aria-label={label} className="-mx-1 flex flex-wrap gap-1.5 px-1">
      {chips.map((chip) => (
        <Link
          key={chip.key}
          href={chip.href}
          scroll={false}
          aria-current={chip.active ? "true" : undefined}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            chip.active ? "border-primary bg-primary text-primary-foreground" : "bg-card text-ink-2 hover:border-primary/50 hover:text-foreground",
            chip.count === 0 && !chip.active && "text-muted-foreground",
          )}
        >
          {chip.label}
          {chip.count !== undefined ? <span className={cn("tabular-nums", chip.active ? "opacity-80" : "text-muted-foreground")}>{formatNumber(chip.count)}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

/** Field chips from the view's options, plus 전체 when `allHref` is given. */
export function fieldChips(view: DomainView, href: (field: string | null) => string, current: string | null, counts?: Map<string, number>, allHref = true): Chip[] {
  const chips: Chip[] = view.field_options.map((option: Option) => ({
    key: option.key,
    label: option.label,
    href: href(option.key),
    active: current === option.key,
    count: counts?.get(option.key),
  }));
  return allHref ? [{ key: "all", label: "전체", href: href(null), active: current === null }, ...chips] : chips;
}

export function EmptyNote({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground", className)}>{children}</p>;
}

/**
 * The daily Opus insight: each sentence ends with links to the documents behind it. Before the
 * first one is published (plan 19 P4) a quiet placeholder takes its place.
 */
export function InsightBlock({ insight, title = "오늘의 인사이트", asOf, compact = false }: { insight: DomainInsight | null | undefined; title?: string; asOf?: string; compact?: boolean }) {
  const sentences = insight?.sentences.filter((s) => s.text.trim()) ?? [];
  if (!insight || !sentences.length) {
    return (
      <section aria-label={title} className={cn("rounded-2xl border border-dashed px-4 text-sm text-muted-foreground", compact ? "py-2.5" : "py-4")}>
        {compact ? null : <h2 className="mb-1 text-[15px] font-bold tracking-tight text-foreground">{title}</h2>}
        인사이트는 매일 05시 브리핑 뒤에 작성됩니다.
      </section>
    );
  }
  let n = 0;
  const stale = asOf && insight.date < asOf;
  return (
    <section aria-label={title} className="rounded-2xl border bg-card px-4 py-4 shadow-xs md:px-5">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-2">
        {compact ? null : <h2 className="text-[15px] font-bold tracking-tight">{title}</h2>}
        <span className="text-xs text-muted-foreground">
          {insight.date.replaceAll("-", ".")} 작성{stale ? " (가장 최근 발행본)" : ""}
        </span>
      </header>
      <ul className="space-y-1.5 text-sm leading-relaxed">
        {sentences.map((sentence, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/70" />
            <span>
              {sentence.text}
              {sentence.doc_ids.map((id) => {
                n += 1;
                return (
                  <Link key={id} href={`/items/${id}`} scroll={false} aria-label={`근거 문헌 ${n}`} className="ml-1 align-super text-[11px] font-semibold text-primary hover:underline">
                    [{n}]
                  </Link>
                );
              })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Field × week counts as a heat table: one hue, mixed toward the surface for lower counts. */
export function HeatmapTable({ heatmap, href }: { heatmap: Heatmap; href: (field: string) => string }) {
  if (!heatmap.rows.length || heatmap.max === 0) return <EmptyNote>최근 12주 동안 집계된 문헌이 없습니다.</EmptyNote>;
  const last = heatmap.weeks.length - 1;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-separate border-spacing-[2px] text-xs">
        <caption className="sr-only">기술분야별 주간 문헌 수 (최근 {heatmap.weeks.length}주, 가장 많은 칸 {heatmap.max}건 기준으로 칠함)</caption>
        <thead>
          <tr className="text-muted-foreground">
            <th scope="col" className="pb-1 text-left font-medium">
              분야
            </th>
            {heatmap.weeks.map((week, i) => (
              <th key={week.start} scope="col" title={spanLabel(week)} className={cn("pb-1 font-medium tabular-nums", i === last && "text-foreground")}>
                {shortDay(week.start)}
              </th>
            ))}
            <th scope="col" className="pb-1 pl-2 text-right font-medium">
              합계
            </th>
          </tr>
        </thead>
        <tbody>
          {heatmap.rows.map((row) => {
            const total = row.counts.reduce((a, b) => a + b, 0);
            return (
              <tr key={row.key}>
                <th scope="row" className="max-w-36 pr-2 text-left font-medium">
                  <Link href={href(row.key)} className="block truncate hover:text-primary">
                    {row.label}
                  </Link>
                </th>
                {row.counts.map((count, i) => {
                  const level = heatLevel(count, heatmap.max);
                  const week = heatmap.weeks[i];
                  return (
                    <td
                      key={week.start}
                      title={`${row.label} · ${spanLabel(week)}: ${count}건`}
                      aria-label={`${row.label} ${spanLabel(week)} ${count}건`}
                      data-level={level}
                      className={cn("h-7 min-w-9 rounded-[5px] text-center tabular-nums", level >= 55 ? "font-semibold text-heat-ink" : count ? "text-ink-2" : "text-transparent")}
                      style={{ background: `color-mix(in oklab, var(--heat) ${level}%, var(--muted))` }}
                    >
                      {count || ""}
                    </td>
                  );
                })}
                <td className="pl-2 text-right font-semibold tabular-nums">{formatNumber(total)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Signal({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold tabular-nums text-ink-2">{value}</span>
    </span>
  );
}

/** One document: what and when, who wrote or filed it, and the signals behind its rank. */
export function DocRow({ doc, domain, companyHref }: { doc: Doc; domain: DomainKind; companyHref?: (key: string) => string }) {
  const research = domain === "research";
  const people = research ? (doc.orgs ?? []) : (doc.applicants ?? []);
  return (
    <article className="flex min-w-0 flex-col gap-1.5 rounded-xl border bg-card px-4 py-3 shadow-xs [content-visibility:auto] [contain-intrinsic-size:auto_120px]">
      <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        <span className="rounded bg-muted px-1.5 py-px font-medium text-ink-2">{doc.field_label}</span>
        <span className="truncate">{research ? (doc.venue ?? doc.source_name) : [doc.publication_number, doc.office].filter(Boolean).join(" · ") || doc.source_name}</span>
        {doc.watched ? <WatchedBadge relation={null} /> : null}
        <time className="ml-auto shrink-0 tabular-nums" dateTime={doc.occurred_at}>
          {formatDay(doc.occurred_at)}
        </time>
      </div>
      <h3 className="line-clamp-2 text-[15px] leading-snug font-semibold">
        <Link href={`/items/${doc.id}`} scroll={false} className="hover:text-primary hover:underline">
          {doc.title_ko ?? doc.title}
        </Link>
      </h3>
      {doc.summary ? <p className="line-clamp-2 text-sm leading-relaxed text-ink-2">{doc.summary}</p> : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {research ? (
          <>
            <Signal label="화제 점수" value={doc.score.toFixed(1)} />
            {doc.mentions ? <Signal label="언급" value={`${doc.mentions}건`} /> : null}
            {doc.upvotes ? <Signal label="HF 추천" value={doc.upvotes} /> : null}
            {doc.cited_by !== null && doc.cited_by !== undefined ? <Signal label="인용" value={formatNumber(doc.cited_by)} /> : null}
          </>
        ) : (
          <>
            <Signal label="보도" value={`${doc.press ?? 0}곳`} />
            {doc.patent_source ? <Signal label="출처" value={doc.patent_source === "news" ? "지식재산 뉴스" : doc.patent_source === "ops" ? "EPO OPS" : "EPO 공보"} /> : null}
          </>
        )}
        {doc.companies.map((company) =>
          companyHref ? (
            <Link key={company.key} href={companyHref(company.key)} className="rounded-full border px-1.5 py-px text-[11px] text-ink-2 hover:border-primary/50 hover:text-foreground">
              {company.label}
            </Link>
          ) : (
            <span key={company.key} className="rounded-full border px-1.5 py-px text-[11px] text-ink-2">
              {company.label}
            </span>
          ),
        )}
        {people.length ? <span className="min-w-0 truncate text-muted-foreground">{people.slice(0, 3).join(", ")}</span> : null}
      </div>
    </article>
  );
}

export function DocList({ docs, domain, empty, companyHref }: { docs: Doc[]; domain: DomainKind; empty: string; companyHref?: (key: string) => string }) {
  if (!docs.length) return <EmptyNote>{empty}</EmptyNote>;
  return (
    <div className="grid gap-2.5 lg:grid-cols-2">
      {docs.map((doc) => (
        <DocRow key={doc.id} doc={doc} domain={domain} companyHref={companyHref} />
      ))}
    </div>
  );
}

export function Pager({ page, pages, href }: { page: number; pages: number; href: (page: number) => string }) {
  if (pages <= 1) return null;
  return (
    <nav aria-label="페이지" className="flex items-center justify-center gap-4 pt-2 text-sm">
      {page > 1 ? <Link href={href(page - 1)}>← 이전</Link> : <span className="text-muted-foreground">← 이전</span>}
      <span className="tabular-nums text-muted-foreground">
        {page} / {pages}
      </span>
      {page < pages ? <Link href={href(page + 1)}>다음 →</Link> : <span className="text-muted-foreground">다음 →</span>}
    </nav>
  );
}
