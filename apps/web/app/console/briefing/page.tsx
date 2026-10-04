import { CircleAlert, CircleCheck, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { DigestView } from "@/components/console/digest-view";
import { EmptyState } from "@/components/console/empty-state";
import { NewsCard } from "@/components/console/news-card";
import { PageHeader } from "@/components/console/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatPercent, TRACK_LABEL } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import type { BriefingOut, BriefingSummary, GateOut } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "데일리 브리핑" };

function gateValue(gate: GateOut): string {
  const ratio = gate.threshold <= 1 && gate.value <= 1 && !gate.name.startsWith("track_");
  if (gate.name === "evidence") return gate.passed ? "충족" : "미충족";
  return ratio ? `${formatPercent(gate.value)} / 기준 ${formatPercent(gate.threshold)}` : `${gate.value} / 기준 ${gate.threshold}`;
}

async function load(date?: string): Promise<BriefingOut | null> {
  try {
    return await api.get<BriefingOut>(date ? `/api/admin/briefings/${date}` : "/api/admin/briefings/latest");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export default async function BriefingPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const [briefing, history] = await Promise.all([
    load(param(sp, "date")),
    api.get<BriefingSummary[]>("/api/admin/briefings", { limit: 14 }),
  ]);
  if (!briefing) {
    return (
      <>
        <PageHeader title="데일리 브리핑" description="매일 04:40 KST 후보 동결, 05:00 KST 품질 게이트 통과 시 발행" />
        <EmptyState title="아직 발행된 브리핑이 없습니다" description="05:00 launchd 작업이 첫 브리핑을 만듭니다." />
      </>
    );
  }
  return (
    <>
      <PageHeader
        title="데일리 브리핑"
        description={`${briefing.briefing_date} · v${briefing.version} · 후보 ${briefing.candidates}건 중 ${briefing.sections.reduce((n, s) => n + s.items.length, 0)}건 선정 · 동결 ${formatDateTime(briefing.frozen_at)} · 발행 ${formatDateTime(briefing.published_at)}`}
        actions={
          <Badge variant={briefing.status === "published" ? "default" : "destructive"}>
            {briefing.status === "published" ? "발행됨" : "게이트 미달·차단"}
          </Badge>
        }
      />
      {briefing.status === "blocked" ? (
        <Alert variant="destructive">
          <ShieldAlert />
          <AlertTitle>품질 게이트 미달로 발행하지 않았습니다</AlertTitle>
          <AlertDescription>
            미달: {briefing.failing.join(", ")}.{" "}
            {briefing.current_date ? (
              <>
                현재 정식 브리핑은 <Link className="underline" href={`/console/briefing?date=${briefing.current_date}`}>{briefing.current_date}</Link>입니다.
              </>
            ) : (
              "아직 정식 브리핑이 없습니다."
            )}
          </AlertDescription>
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">품질 게이트</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {briefing.gates.map((gate) => (
            <div key={gate.name} className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm", !gate.passed && gate.blocking && "border-destructive/50 bg-destructive/5")}>
              {gate.passed ? <CircleCheck className="size-4 text-emerald-600" /> : <CircleAlert className={cn("size-4", gate.blocking ? "text-destructive" : "text-amber-500")} />}
              <span className="min-w-0 flex-1 truncate">{gate.label}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{gateValue(gate)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
      {briefing.digest ? <DigestView digest={briefing.digest} /> : null}
      {briefing.sections.map((section) => (
        <section key={section.track} className="space-y-3">
          <h2 className="text-lg font-semibold">
            {TRACK_LABEL[section.track]} <span className="text-sm font-normal text-muted-foreground">{section.items.length}건</span>
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 [&>*]:min-w-0">
            {section.items.map((view) => (
              <NewsCard key={view.item.id} view={view} />
            ))}
          </div>
        </section>
      ))}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">발행 이력</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {history.map((entry) => (
            <Button key={`${entry.briefing_date}-${entry.version}`} asChild size="sm" variant={entry.status === "published" ? "outline" : "ghost"}>
              <Link href={`/console/briefing?date=${entry.briefing_date}`} title={entry.failing.join(", ") || "모든 게이트 통과"}>
                {entry.briefing_date} v{entry.version} {entry.status === "blocked" ? "· 차단" : ""}
              </Link>
            </Button>
          ))}
        </CardContent>
      </Card>
    </>
  );
}
