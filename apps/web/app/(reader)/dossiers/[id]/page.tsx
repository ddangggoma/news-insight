import { Pencil } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { archiveDossier } from "@/app/(reader)/dossiers/actions";
import { ExportLinks } from "@/components/reader/export-links";
import { CompanyChips } from "@/components/reader/labels";
import { DossierHypotheses } from "@/components/reader/dossier-hypotheses";
import { StoryRow } from "@/components/reader/story-row";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import { dossierApi } from "@/lib/dossier-api";
import type { DossierDetail, TimelineStory } from "@/lib/dossier-types";
import { formatDateTime } from "@/lib/format";
import { pageParam, type SearchParams } from "@/lib/params";
import type { FeedPage } from "@/lib/reader-types";
import { SIGNAL_LABEL } from "@/lib/taxonomy";
import { NODE_LABEL } from "@/lib/taxonomy-live";
import { loadTaxonomy } from "@/lib/taxonomy-server";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "주제 파일", robots: { index: false } };

function change(now: number, before: number): string {
  if (before === 0) return now ? "새로 등장" : "변화 없음";
  const pct = Math.round(((now - before) / before) * 100);
  return pct === 0 ? "지난주와 같음" : `지난주 대비 ${pct > 0 ? "+" : ""}${pct}%`;
}

function StoryLinks({ stories }: { stories: TimelineStory[] }) {
  return (
    <ul className="space-y-1">
      {stories.map((s) => (
        <li key={s.item_id} className="text-sm">
          <Link href={`/items/${s.item_id}`} scroll={false} className="hover:underline">
            {s.title}
          </Link>
          {s.source_count > 1 ? <span className="ml-1 text-xs text-muted-foreground">· {s.source_count}개 매체</span> : null}
        </li>
      ))}
    </ul>
  );
}

export default async function DossierPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<SearchParams> }) {
  await requireUser();
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id < 1) notFound();
  const page = pageParam(await searchParams);
  const [dossier, items] = await Promise.all([
    dossierApi<DossierDetail>("GET", `/${id}`),
    dossierApi<FeedPage>("GET", `/${id}/items?page=${page}&size=20`),
    loadTaxonomy(),
  ]).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });
  const { criteria, changes } = dossier;
  const peak = Math.max(1, ...dossier.timeline.map((w) => w.items));
  const pages = Math.max(1, Math.ceil(items.total / items.size));
  const busyWeeks = [...dossier.timeline].reverse().filter((w) => w.top.length).slice(0, 6);

  return (
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            <Link href="/dossiers" className="hover:underline">
              주제 파일
            </Link>
          </p>
          <h1 className="text-xl font-semibold">{dossier.title}</h1>
          {dossier.description ? <p className="mt-1 text-sm text-muted-foreground">{dossier.description}</p> : null}
          <p className="mt-1 text-xs text-muted-foreground">
            {formatDateTime(dossier.updated_at)} 수정{dossier.updated_by ? ` · ${dossier.updated_by}` : ""}
            {dossier.created_by ? ` · 만든 사람 ${dossier.created_by}` : ""}
          </p>
          <ExportLinks path={`dossier/${id}`} />
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href={`/dossiers/${id}/edit`}>
            <Pencil className="size-4" aria-hidden />
            편집
          </Link>
        </Button>
        <form action={archiveDossier.bind(null, id)}>
          <Button type="submit" variant="ghost" size="sm">
            보관
          </Button>
        </form>
      </div>

      <div className="flex flex-wrap gap-1.5 text-xs" aria-label="수집 조건">
        {criteria.statement ? (
          <span className="rounded-full border px-2 py-0.5">
            의미: {criteria.statement} (≥{criteria.min_similarity.toFixed(2)}){criteria.semantic_active ? "" : " · 임베딩 대기"}
          </span>
        ) : null}
        {criteria.nodes.map((n) => (
          <span key={n} className="rounded-full border px-2 py-0.5">
            분류: {NODE_LABEL[n] ?? n}
          </span>
        ))}
        {criteria.companies.map((c) => (
          <span key={c.key} className="rounded-full border px-2 py-0.5">
            기업: {c.label}
          </span>
        ))}
        {criteria.keywords.map((k) => (
          <span key={k} className="rounded-full border px-2 py-0.5">
            키워드: {k}
          </span>
        ))}
        {criteria.exclude.map((k) => (
          <span key={k} className="rounded-full border border-dashed px-2 py-0.5 text-muted-foreground">
            제외: {k}
          </span>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-base">최근 7일 바뀐 점</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>
              <strong className="text-lg tabular-nums">{changes.recent}</strong>건 <span className="text-muted-foreground">({change(changes.recent, changes.previous)}, 직전 7일 {changes.previous}건)</span>
            </p>
            {changes.new_companies.length ? (
              <div>
                <p className="mb-1 text-xs text-muted-foreground">새로 등장한 기업</p>
                <CompanyChips companies={changes.new_companies} max={8} />
              </div>
            ) : null}
            {changes.signals.length ? (
              <p className="text-xs text-muted-foreground">
                신호:{" "}
                {changes.signals
                  .slice(0, 4)
                  .map((s) => `${SIGNAL_LABEL[s.key] ?? s.key} ${s.now}(${s.now - s.before >= 0 ? "+" : ""}${s.now - s.before})`)
                  .join(" · ")}
              </p>
            ) : null}
            {changes.top.length ? <StoryLinks stories={changes.top} /> : <p className="text-muted-foreground">최근 7일 새 카드가 없습니다.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-base">주별 흐름 (12주, 카드 {dossier.total}건)</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex h-28 items-end gap-1" role="img" aria-label="주별 카드 수">
              {dossier.timeline.map((w) => (
                <div key={w.week} className="flex flex-1 flex-col items-center gap-1" title={`${w.week} 주: ${w.items}건, 이슈 ${w.stories}개`}>
                  <div className="w-full rounded-t bg-primary/70" style={{ height: `${Math.max(2, (w.items / peak) * 96)}px` }} />
                  <span className="text-[10px] text-muted-foreground tabular-nums">{w.week.slice(5).replace("-", "/")}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-5">
          <DossierHypotheses dossierId={id} initial={dossier.hypotheses} />
          <section aria-labelledby="timeline-heading" className="space-y-3">
            <h2 id="timeline-heading" className="text-base font-semibold">
              타임라인 (주별 주요 이슈)
            </h2>
            {busyWeeks.length ? (
              <ol className="space-y-3 border-l pl-4">
                {busyWeeks.map((w) => (
                  <li key={w.week}>
                    <p className="text-xs font-medium text-muted-foreground">
                      {w.week} 주 · {w.items}건 · 이슈 {w.stories}개
                    </p>
                    <StoryLinks stories={w.top} />
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">조건에 맞는 카드가 아직 없습니다.</p>
            )}
          </section>
          <section aria-labelledby="cards-heading">
            <h2 id="cards-heading" className="text-base font-semibold">
              카드 (90일, 이슈 {items.total}개)
            </h2>
            {items.items.map((item) => (
              <StoryRow key={item.id} item={item} />
            ))}
            {pages > 1 ? (
              <nav aria-label="페이지" className="flex items-center justify-center gap-4 pt-2 text-sm">
                {page > 1 ? <Link href={`/dossiers/${id}?page=${page - 1}`}>← 이전</Link> : <span className="text-muted-foreground">← 이전</span>}
                <span className="tabular-nums text-muted-foreground">
                  {page} / {pages}
                </span>
                {page < pages ? <Link href={`/dossiers/${id}?page=${page + 1}`}>다음 →</Link> : <span className="text-muted-foreground">다음 →</span>}
              </nav>
            ) : null}
          </section>
        </div>
        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="text-base">관련 기업</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dossier.companies.length ? (
                <ul className="space-y-1 text-sm">
                  {dossier.companies.map(({ company, count }) => (
                    <li key={company.key} className="flex justify-between gap-2">
                      <Link href={`/?company=${encodeURIComponent(company.key)}`} className="hover:underline">
                        {company.label}
                      </Link>
                      <span className="text-muted-foreground tabular-nums">{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">등록된 기업이 나온 카드가 없습니다.</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="text-base">핵심 수치 (30일)</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dossier.figures.length ? (
                <ul className="space-y-2 text-sm">
                  {dossier.figures.map((f) => (
                    <li key={`${f.item_id}-${f.text}`}>
                      <Link href={`/items/${f.item_id}`} scroll={false} className="hover:underline">
                        {f.text}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {f.source} · {formatDateTime(f.first_seen_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">수치가 담긴 요약이 없습니다.</p>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </main>
  );
}
