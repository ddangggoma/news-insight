import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { OutcomeBadge, StageBadge, StatusBadge, TrackBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { SourceActions } from "@/components/console/source-actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL, formatDateTime, formatNumber, formatRelative, REGION_LABEL } from "@/lib/format";
import type { ItemRow, RunOut, SourceDetail } from "@/lib/types";

const runColumns: Column<RunOut>[] = [
  { key: "time", header: "시작", className: "text-muted-foreground", cell: (run) => formatDateTime(run.started_at) },
  { key: "outcome", header: "결과", cell: (run) => <OutcomeBadge outcome={run.outcome} /> },
  { key: "http", header: "HTTP", className: "font-mono", cell: (run) => run.http_status ?? "—" },
  { key: "items", header: "신규/변경/동일", className: "tabular-nums", cell: (run) => `${run.items_new} / ${run.items_updated} / ${run.items_unchanged}` },
  { key: "elapsed", header: "지연", className: "tabular-nums text-muted-foreground", cell: (run) => (run.elapsed_ms ? `${run.elapsed_ms}ms` : "—") },
  { key: "error", header: "오류", className: "max-w-xs truncate text-destructive", cell: (run) => run.error_code ?? "" },
];

const itemColumns: Column<ItemRow>[] = [
  {
    key: "title",
    header: "제목",
    cell: (item) => (
      <Link href={`/console/items/${item.id}`} className="hover:underline">
        {item.title}
      </Link>
    ),
  },
  { key: "published", header: "발행", className: "w-28 text-muted-foreground", cell: (item) => formatDateTime(item.published_at) },
  { key: "seen", header: "수집", className: "w-24 text-muted-foreground", cell: (item) => formatRelative(item.first_seen_at) },
];

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  return { title: `소스 ${key}` };
}

export default async function SourcePage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  let detail: SourceDetail;
  try {
    detail = await api.get<SourceDetail>(`/api/admin/sources/${encodeURIComponent(key)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const { source } = detail;
  const facts: [string, React.ReactNode][] = [
    ["엔드포인트", <a key="e" href={detail.endpoint_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all hover:underline">{detail.endpoint_url} <ExternalLink className="size-3" /></a>],
    ["공식 도메인", detail.official_domain],
    ["운영 주체", detail.operator],
    ["범주", CATEGORY_LABEL[source.category] ?? source.category],
    ["지역·언어", `${REGION_LABEL[source.region]} · ${detail.language}`],
    ["접근 방식", source.access_method],
    ["수집 주기", source.interval_seconds ? `${Math.round(source.interval_seconds / 60)}분 (${detail.poll_class})` : detail.poll_class],
    ["다음 수집", formatRelative(source.next_due_at)],
    ["원문 저장", detail.storage_right ?? "미정"],
    ["약관", detail.terms_url ? <a key="t" href={detail.terms_url} target="_blank" rel="noreferrer" className="hover:underline">{detail.terms_url}</a> : <span className="text-destructive">미검토 (V1 대기)</span>],
    ["DX 연관성", detail.dx_relevance],
  ];
  return (
    <>
      <PageHeader
        title={source.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{source.key}</span>
            <TrackBadge track={source.track} />
            <StageBadge stage={source.validation_stage} />
            <StatusBadge status={source.status} />
            {source.paused_reason ? <Badge variant="outline">{source.paused_reason}</Badge> : null}
          </span>
        }
        actions={<SourceActions sourceKey={source.key} status={source.status} />}
      />
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">개요</TabsTrigger>
          <TabsTrigger value="events">검증 이력</TabsTrigger>
          <TabsTrigger value="runs">최근 실행</TabsTrigger>
          <TabsTrigger value="items">최근 항목 ({formatNumber(source.items_total)})</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <Card>
            <CardContent className="pt-6">
              <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {facts.map(([label, value]) => (
                  <div key={label} className="space-y-1">
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd className="text-sm">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="events">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">검증 이력 (최신순)</CardTitle>
            </CardHeader>
            <CardContent>
              {detail.events.length === 0 ? (
                <p className="text-sm text-muted-foreground">아직 검증을 실행하지 않았습니다.</p>
              ) : (
                <ol className="relative space-y-4 border-l pl-6">
                  {detail.events.map((event) => (
                    <li key={`${event.stage}-${event.created_at}`} className="space-y-1">
                      <span className={`absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-background ${event.outcome === "passed" ? "bg-emerald-500" : event.outcome === "failed" ? "bg-destructive" : "bg-muted-foreground"}`} />
                      <div className="flex items-center gap-2 text-sm">
                        <StageBadge stage={event.stage} />
                        <span className="font-medium">{event.outcome === "passed" ? "통과" : event.outcome === "failed" ? "실패" : "초기화"}</span>
                        <span className="text-muted-foreground">{formatDateTime(event.created_at)}</span>
                      </div>
                      {event.reasons.length ? <p className="text-sm text-muted-foreground">{event.reasons.join(" · ")}</p> : null}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="runs">
          <DataTable columns={runColumns} rows={detail.runs} rowKey={(run) => run.id} emptyTitle="실행 기록이 없습니다" />
        </TabsContent>
        <TabsContent value="items">
          <DataTable columns={itemColumns} rows={detail.items} rowKey={(item) => item.id} emptyTitle="수집된 항목이 없습니다" />
        </TabsContent>
      </Tabs>
    </>
  );
}
