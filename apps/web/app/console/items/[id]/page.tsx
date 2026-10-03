import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { TrackBadge } from "@/components/console/badges";
import { PageHeader } from "@/components/console/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABEL, formatDateTime, formatNumber, REGION_LABEL } from "@/lib/format";
import type { ItemDetail } from "@/lib/types";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return { title: `항목 #${id}` };
}

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let detail: ItemDetail;
  try {
    detail = await api.get<ItemDetail>(`/api/admin/items/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const { item } = detail;
  return (
    <>
      <PageHeader
        title={item.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <TrackBadge track={item.track} />
            <Link href={`/console/sources/${item.source_key}`} className="hover:underline">{item.source_name}</Link>
            <span>· {CATEGORY_LABEL[item.category] ?? item.category} · {REGION_LABEL[item.region]}</span>
            {item.canary ? <Badge variant="outline">Canary</Badge> : null}
          </span>
        }
        actions={
          <Button asChild size="sm">
            <a href={item.url} target="_blank" rel="noreferrer">원문 열기 <ExternalLink /></a>
          </Button>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-base">내용</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed">
            {detail.summary ?? detail.body ? <p className="whitespace-pre-line">{detail.summary ?? detail.body}</p> : <p className="text-muted-foreground">이 소스는 원문 저장 등급이 metadata_only라 제목·링크만 저장합니다.</p>}
            <dl className="grid grid-cols-2 gap-3 pt-2 text-xs text-muted-foreground">
              <div><dt>발행</dt><dd className="text-foreground">{formatDateTime(item.published_at)}</dd></div>
              <div><dt>처음 수집</dt><dd className="text-foreground">{formatDateTime(item.first_seen_at)}</dd></div>
              <div><dt>저자</dt><dd className="text-foreground">{detail.author ?? "—"}</dd></div>
              <div><dt>리비전</dt><dd className="text-foreground">{item.revision}</dd></div>
            </dl>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">지표 이력</CardTitle></CardHeader>
            <CardContent>
              {detail.metric_history.length === 0 ? <p className="text-sm text-muted-foreground">지표가 없는 항목입니다.</p> : (
                <ul className="space-y-2 text-sm">
                  {detail.metric_history.map((point) => (
                    <li key={point.captured_at} className="flex justify-between gap-2">
                      <span className="text-muted-foreground">{formatDateTime(point.captured_at)}</span>
                      <span className="tabular-nums">{Object.entries(point.metrics).map(([k, v]) => `${k} ${formatNumber(v)}`).join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">리비전</CardTitle></CardHeader>
            <CardContent>
              <ol className="space-y-2 text-sm">
                {detail.revisions.map((revision) => (
                  <li key={revision.revision} className="flex gap-2">
                    <Badge variant="outline" className="font-mono">r{revision.revision}</Badge>
                    <span className="min-w-0 flex-1 truncate">{revision.title}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatDateTime(revision.recorded_at)}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
