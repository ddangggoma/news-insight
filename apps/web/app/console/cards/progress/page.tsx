import { CheckCircle2, Clock, Copy, Gauge, Hourglass, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { DailyEngineChart, FlowChart, HourlyEngineChart, StateBar } from "@/components/console/card-progress-charts";
import { PageHeader } from "@/components/console/page-header";
import { StatCard } from "@/components/console/stat-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { engineGroup, ENGINES, STATE_LABEL } from "@/lib/card-progress";
import { CATEGORY_LABEL, formatDateTime, formatNumber, formatPercent, formatRelative, REGION_LABEL, STATUS_LABEL, TRACK_LABEL } from "@/lib/format";
import type { CardProgress, ProgressRow, ProgressState } from "@/lib/types";

export const metadata = { title: "카드 처리 현황" };

const ENGINE_LABEL: Record<string, string> = {
  agy: "Antigravity",
  "agy-claude": "Antigravity Claude·GPT",
  codex: "Codex",
  claude: "Claude",
  qwen: "로컬 Qwen",
  reuse: "재사용(복사)",
  other: "기타",
};
const LANGUAGE_LABEL: Record<string, string> = {
  en: "영어",
  ko: "한국어",
  ja: "일본어",
  zh: "중국어(간체)",
  "zh-TW": "중국어(번체)",
  "zh-HK": "중국어(홍콩)",
  de: "독일어",
  fr: "프랑스어",
  it: "이탈리아어",
  es: "스페인어",
  pl: "폴란드어",
  nl: "네덜란드어",
  pt: "포르투갈어",
};
const KIND_LABEL: Record<string, string> = { url: "같은 URL", text: "같은 본문", link: "공유 링크", title: "같은 제목" };
const DIMENSIONS: { key: keyof CardProgress["breakdown"]; title: string; label: (key: string) => string }[] = [
  { key: "status", title: "소스 상태", label: (k) => STATUS_LABEL[k as keyof typeof STATUS_LABEL] ?? k },
  { key: "track", title: "트랙", label: (k) => TRACK_LABEL[k as keyof typeof TRACK_LABEL] ?? k },
  { key: "category", title: "카테고리", label: (k) => CATEGORY_LABEL[k] ?? k },
  { key: "region", title: "지역", label: (k) => REGION_LABEL[k as keyof typeof REGION_LABEL] ?? k },
  { key: "language", title: "언어", label: (k) => LANGUAGE_LABEL[k] ?? k },
];
const COLUMNS: ProgressState[] = ["ready", "pending", "capped", "repeat", "failed", "held", "archive"];

/** Ready over everything that can get a card (archive and held items never do). */
function doneRatio(row: Pick<ProgressRow, "ready" | "total" | "archive" | "held">): number {
  const cardable = row.total - row.archive - row.held;
  return cardable > 0 ? row.ready / cardable : Number.NaN;
}

function QuotaMeter({ label, value }: { label: string; value: number | null }) {
  const pct = value ?? 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-medium tabular-nums text-foreground">{value === null ? "—" : `${value}% 남음`}</span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-foreground/70" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
        {/* the 10 % reserve the scheduled runs keep */}
        <div className="absolute inset-y-0 left-[10%] w-px bg-destructive" aria-hidden />
      </div>
    </div>
  );
}

export default async function CardProgressPage() {
  const p = await api.get<CardProgress>("/api/admin/cards/progress");
  const t = p.totals;
  const today = p.days.at(-1);
  const todayCards = today ? Object.values(today.cards).reduce((sum, n) => sum + n, 0) : 0;
  const waiting = t.pending + t.capped + t.repeat;
  const kinds = Object.entries(p.repeats_by_kind)
    .sort((a, b) => b[1] - a[1])
    .map(([kind, n]) => `${KIND_LABEL[kind] ?? kind} ${formatNumber(n)}`)
    .join(" · ");

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6">
      <PageHeader
        title="카드 처리 현황"
        description={`수집한 모든 기사의 카드 상태, 엔진별 생성량, 한도와 최근 실행 · ${formatRelative(p.generated_at)} 기준 (최대 1분 지연)`}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/console/cards">카드 뉴스로</Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-6 [&>*]:min-w-0">
        <StatCard title="처리 완료" value={formatNumber(t.ready)} hint={`카드 대상의 ${formatPercent(doneRatio({ ...t, total: t.items }))}`} icon={CheckCircle2} />
        <StatCard title="대기 합계" value={formatNumber(waiting)} hint={`처리 ${formatNumber(t.pending)} · 상한 ${formatNumber(t.capped)} · 복사 ${formatNumber(t.repeat)}`} icon={Clock} />
        <StatCard title="오늘 생성" value={formatNumber(todayCards)} hint={`오늘 수집 ${formatNumber(today?.inflow ?? 0)}건`} icon={Gauge} />
        <StatCard title="중복 복사" value={formatNumber(t.copied)} hint={kinds || "—"} icon={Copy} />
        <StatCard title="실패(포기)" value={formatNumber(t.failed)} hint="3회 시도 후" icon={TriangleAlert} />
        <StatCard title="카드 제외" value={formatNumber(t.archive + t.held)} hint={`아카이브 ${formatNumber(t.archive)} · 보류 ${formatNumber(t.held)}`} icon={Hourglass} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>수집 기사 상태</CardTitle>
          <CardDescription>전체 {formatNumber(t.items)}건이 지금 어느 단계에 있는지</CardDescription>
        </CardHeader>
        <CardContent>
          <StateBar totals={t} />
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
        <Card>
          <CardHeader>
            <CardTitle>일별 카드 생성 (엔진별)</CardTitle>
            <CardDescription>최근 14일, KST 기준</CardDescription>
          </CardHeader>
          <CardContent>
            <DailyEngineChart days={p.days} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>신규 수집 대 카드 생성</CardTitle>
            <CardDescription>카드가 수집을 앞서면 대기가 줄어듭니다</CardDescription>
          </CardHeader>
          <CardContent>
            <FlowChart days={p.days} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3 [&>*]:min-w-0">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>최근 48시간 (시간대별)</CardTitle>
            <CardDescription>엔진별 카드 생성</CardDescription>
          </CardHeader>
          <CardContent>
            <HourlyEngineChart hours={p.hours} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>엔진 한도</CardTitle>
            <CardDescription>마지막 실행에서 읽은 남은 비율 · 붉은 선은 정기 실행 예비분(10%)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {p.quotas.length === 0 ? <p className="text-sm text-muted-foreground">최근 3일 기록 없음</p> : null}
            {p.quotas.map((q) => (
              <div key={q.engine} className="space-y-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium">{ENGINE_LABEL[q.engine] ?? q.engine}</span>
                  <span className="text-xs text-muted-foreground">{formatRelative(q.seen_at)}</span>
                </div>
                {q.engine === "claude" ? (
                  <p className="text-xs text-muted-foreground">Claude CLI는 남은 한도를 알려주지 않습니다</p>
                ) : (
                  <>
                    <QuotaMeter label="주간" value={q.weekly} />
                    <QuotaMeter label="5시간" value={q.five_hour} />
                  </>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>구분별 현황</CardTitle>
          <CardDescription>완료율 = 완료 ÷ (전체 − 아카이브 − 보류)</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="status" className="min-w-0">
            <TabsList>
              {DIMENSIONS.map((d) => (
                <TabsTrigger key={d.key} value={d.key}>
                  {d.title}
                </TabsTrigger>
              ))}
            </TabsList>
            {DIMENSIONS.map((d) => (
              <TabsContent key={d.key} value={d.key} className="min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{d.title}</TableHead>
                      <TableHead className="text-right">전체</TableHead>
                      {COLUMNS.map((c) => (
                        <TableHead key={c} className="text-right">
                          {STATE_LABEL[c]}
                        </TableHead>
                      ))}
                      <TableHead className="text-right">완료율</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {p.breakdown[d.key].map((row) => (
                      <TableRow key={row.key}>
                        <TableCell className="font-medium">{d.label(row.key)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatNumber(row.total)}</TableCell>
                        {COLUMNS.map((c) => (
                          <TableCell key={c} className={`text-right tabular-nums ${row[c] === 0 ? "text-muted-foreground/50" : ""}`}>
                            {formatNumber(row[c])}
                          </TableCell>
                        ))}
                        <TableCell className="text-right tabular-nums">{formatPercent(doneRatio(row))}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>일별 표</CardTitle>
          <CardDescription>위 일별 차트의 숫자</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>날짜</TableHead>
                <TableHead className="text-right">신규 수집</TableHead>
                {ENGINES.map((e) => (
                  <TableHead key={e} className="text-right">
                    {ENGINE_LABEL[e]}
                  </TableHead>
                ))}
                <TableHead className="text-right">카드 합계</TableHead>
                <TableHead className="text-right">실패</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...p.days].reverse().map((d) => (
                <TableRow key={d.date}>
                  <TableCell className="tabular-nums">{d.date}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(d.inflow)}</TableCell>
                  {ENGINES.map((e) => (
                    <TableCell key={e} className="text-right tabular-nums">
                      {formatNumber(Object.entries(d.cards).reduce((s, [k, n]) => s + (engineGroup(k) === e ? n : 0), 0))}
                    </TableCell>
                  ))}
                  <TableCell className="text-right font-medium tabular-nums">{formatNumber(Object.values(d.cards).reduce((s, n) => s + n, 0))}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(d.failed)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>최근 카드 실행</CardTitle>
          <CardDescription>최근 30회 (정기·집중 실행 모두)</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>시작</TableHead>
                <TableHead className="text-right">완료</TableHead>
                <TableHead className="text-right">실패</TableHead>
                <TableHead>엔진 묶음</TableHead>
                <TableHead>한도</TableHead>
                <TableHead>메모</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {p.runs.map((r) => (
                <TableRow key={r.started_at}>
                  <TableCell className="tabular-nums text-muted-foreground">{formatDateTime(r.started_at)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(r.ready)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(r.failed)}</TableCell>
                  <TableCell className="text-sm">
                    {Object.entries(r.batches)
                      .map(([e, n]) => `${ENGINE_LABEL[e] ?? e} ${n}`)
                      .join(" · ") || "—"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {r.quota.engine ? `${ENGINE_LABEL[String(r.quota.engine)] ?? r.quota.engine} 주간 ${r.quota.weekly ?? "—"}% · 5시간 ${r.quota.five_hour ?? "—"}%` : "—"}
                  </TableCell>
                  <TableCell className="max-w-md truncate text-sm text-muted-foreground" title={r.note ?? undefined}>
                    {r.note ?? ""}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
