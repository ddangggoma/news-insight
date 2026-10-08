import Link from "next/link";
import { notFound } from "next/navigation";

import { RadarBoard } from "@/components/reader/radar/board";
import { RadarControls } from "@/components/reader/radar/controls";
import { SectionNav } from "@/components/reader/radar/section-nav";
import { ApiError } from "@/lib/api";
import type { SearchParams } from "@/lib/params";
import { BASELINE_UNIT, initialFocus, isRadarKind, RADAR_KINDS, radarFilters, type RadarView } from "@/lib/radar";
import { radarView } from "@/lib/radar-view";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { Radar, TopicDetail } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";

type Props = { params: Promise<{ period: string; key: string }>; searchParams: Promise<SearchParams> };

async function load<T>(path: string, query: Record<string, string | string[] | undefined>): Promise<T> {
  try {
    return await readerGet<T>(path, query, REVALIDATE.radarOpen);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Props) {
  const { period, key } = await params;
  return { title: `${isRadarKind(period) ? RADAR_KINDS[period] : ""} 기술 레이더 ${key}` };
}

export default async function RadarPage({ params, searchParams }: Props) {
  const [{ period, key }, sp] = await Promise.all([params, searchParams]);
  if (!isRadarKind(period)) notFound();
  const requested = radarView(sp);
  const filters = radarFilters(requested);
  const topic = (view: RadarView) =>
    view.focus ? load<TopicDetail>("/radar/topic", { period, key, ...filters, kind: view.focus.kind, value: view.focus.key }) : null;
  const [radar, requestedDetail] = await Promise.all([load<Radar>("/radar", { period, key, ...filters }), topic(requested)]);
  const view: RadarView = { ...requested, focus: initialFocus(radar, requested.focus) };
  const detail = requestedDetail ?? (await topic(view));
  const unit = `직전 ${radar.periods.length - 1}${BASELINE_UNIT[radar.window.kind]}`;

  return (
    <main className="mx-auto max-w-[1480px] space-y-5 px-4 py-5 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            기술 레이더 <span className="text-muted-foreground">{RADAR_KINDS[radar.window.kind]} {radar.window.key}</span>
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {view.field ? `${FIELD_LABEL[view.field]} 카테고리의 ` : ""}테마·기술 언급 흐름, 부상 신호, 연구→시장 이동을 {unit} 기준선과 비교합니다.
          </p>
        </div>
      </header>
      {radar.taxonomy_revised_on && radar.window.start && radar.window.start.slice(0, 10) <= radar.taxonomy_revised_on ? (
        <p role="note" className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
          기술 분류 체계가 {radar.taxonomy_revised_on}에 개정되었습니다(12개 기술 분야·62개 테마·신호 유형). 그 이전 기간은 새 체계로 다시 분류하는 중이라, 이전 기간과의 증감·추세는 참고용으로 보세요.
        </p>
      ) : null}
      <p className="text-sm">
        <Link href={`/radar/${period}/${key}/taxonomy`} className="font-medium text-primary hover:underline">
          분류 탐색 →
        </Link>
        <span className="ml-2 text-muted-foreground">체계·깊이를 골라 트리맵으로 보기</span>
      </p>
      <RadarControls radar={radar} view={view} />
      <SectionNav />

      <RadarBoard radar={radar} view={view} detail={detail} unit={unit} />
    </main>
  );
}
