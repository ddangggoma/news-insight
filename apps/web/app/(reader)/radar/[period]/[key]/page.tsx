import Link from "next/link";
import { notFound } from "next/navigation";

import {
  CellPanel,
  Heatmap,
  HeatmapTable,
  HypeScatter,
  KeywordShifts,
  KpiStrip,
  MomentumTable,
  RadarControls,
  radarHref,
  type RadarView,
} from "@/components/reader/radar";
import { ApiError } from "@/lib/api";
import { param, type SearchParams } from "@/lib/params";
import { heatRows, initialCell, isRadarKind, parseCell, RADAR_KINDS } from "@/lib/radar";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import type { CellDetail, Radar } from "@/lib/reader-types";

type Props = { params: Promise<{ period: string; key: string }>; searchParams: Promise<SearchParams> };

async function loadRadar(period: string, key: string, scope: Scope): Promise<Radar> {
  if (!isRadarKind(period)) notFound();
  try {
    return await readerGet<Radar>("/radar", { period, key, scope }, REVALIDATE.radarOpen);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Props) {
  const { period, key } = await params;
  return { title: `${isRadarKind(period) ? RADAR_KINDS[period] : ""} 레이더 ${key}` };
}

function Box({ title, note, children, action }: { title: string; note?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-xl border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold">{title}</h2>
        {note ? <span className="text-xs text-muted-foreground">{note}</span> : null}
        {action}
      </div>
      {children}
    </section>
  );
}

export default async function RadarPage({ params, searchParams }: Props) {
  const [{ period, key }, sp] = await Promise.all([params, searchParams]);
  const scopeParam = param(sp, "scope");
  const scope: Scope = scopeParam && scopeParam in SCOPES ? (scopeParam as Scope) : "relevant";
  const radar = await loadRadar(period, key, scope);
  const view: RadarView = {
    scope,
    cell: initialCell(radar, parseCell(param(sp, "cell"))),
    table: param(sp, "view") === "table",
    allRows: param(sp, "rows") === "all",
  };
  const detail = view.cell
    ? await readerGet<CellDetail>(
        "/radar/cell",
        { period, key: radar.window.key, field: view.cell.field, business: view.cell.business, scope },
        REVALIDATE.radarOpen,
      )
    : null;
  const { kind } = radar.window;

  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-4 py-5 md:px-6">
      <h1 className="sr-only">
        {RADAR_KINDS[kind]} 레이더 {radar.window.key}
      </h1>
      <RadarControls radar={radar} view={view} />
      <KpiStrip radar={radar} />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)] lg:items-start">
        <Box
          title="기술 분야 × DX 사업부"
          note="칸 = 기사 수 · 아래 = 직전 기간 대비"
          action={
            <span className="flex gap-3 text-xs">
              <Link href={radarHref(kind, radar.window.key, { ...view, table: !view.table })} scroll={false} className="text-primary hover:underline">
                {view.table ? "히트맵으로 보기" : "표로 보기"}
              </Link>
              {!view.table ? (
                <Link href={radarHref(kind, radar.window.key, { ...view, allRows: !view.allRows })} scroll={false} className="text-primary hover:underline">
                  {view.allRows ? "상위 12개 분야만" : "전체 15개 분야"}
                </Link>
              ) : null}
            </span>
          }
        >
          {view.table ? <HeatmapTable radar={radar} /> : <Heatmap radar={radar} rows={heatRows(radar, view.allRows ? undefined : 12)} view={view} />}
        </Box>
        <section className="min-w-0 rounded-xl border bg-card p-4 lg:sticky lg:top-20" aria-live="polite">
          {detail ? <CellPanel detail={detail} radar={radar} scope={scope} /> : <p className="text-sm text-muted-foreground">이 기간에 분류된 기사가 아직 없습니다.</p>}
        </section>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Box title="분야 모멘텀" note="직전 기간 대비 · 최근 8개 기간">
          <MomentumTable radar={radar} />
        </Box>
        <Box title="관심 대비 실체" note="가로 = 뉴스·커뮤니티, 세로 = 논문·오픈소스 증감률">
          <HypeScatter radar={radar} />
        </Box>
      </div>
      <Box title="키워드 변화" note="이번 기간과 직전 4개 기간 비교">
        <KeywordShifts radar={radar} />
      </Box>
    </main>
  );
}
