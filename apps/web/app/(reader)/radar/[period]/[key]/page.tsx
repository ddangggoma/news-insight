import { notFound } from "next/navigation";

import { RadarControls } from "@/components/reader/radar/controls";
import { FocusScroll } from "@/components/reader/radar/focus-scroll";
import { CategoryTreemap, PositioningMatrix, TimingHeatmap } from "@/components/reader/radar/landscape";
import { KpiStrip, SignalCards } from "@/components/reader/radar/overview";
import { Panel } from "@/components/reader/radar/parts";
import { CategoryShare, MaturityBars } from "@/components/reader/radar/structure";
import { ConvergenceNetwork, EmergingTable, PairList, TechCloud } from "@/components/reader/radar/technology";
import { TopicPanel } from "@/components/reader/radar/topic-panel";
import { ApiError } from "@/lib/api";
import type { SearchParams } from "@/lib/params";
import { BASELINE_UNIT, focusParam, initialFocus, isRadarKind, RADAR_KINDS, radarFilters, type RadarView } from "@/lib/radar";
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
      <RadarControls radar={radar} view={view} />

      <section aria-labelledby="signals-title" className="space-y-3">
        <h2 id="signals-title" className="text-sm font-bold">
          지금 볼 신호 <span className="font-normal text-muted-foreground">· 눌러서 오른쪽에서 자세히</span>
        </h2>
        <SignalCards radar={radar} view={view} />
      </section>
      <KpiStrip radar={radar} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
        <aside aria-label="선택한 항목" aria-live="polite" className="min-w-0 lg:sticky lg:top-20 lg:order-2 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:overscroll-contain">
          <FocusScroll focusKey={view.focus ? focusParam(view.focus) : ""}>
            <div className="rounded-2xl border bg-card p-4 shadow-xs md:p-5">
              {detail ? <TopicPanel detail={detail} radar={radar} view={view} /> : <p className="text-sm text-muted-foreground">이 기간에 분류된 기사가 아직 없습니다.</p>}
            </div>
          </FocusScroll>
        </aside>

        <div className="min-w-0 space-y-5 lg:order-1">
          <Panel
            id="landscape"
            title="카테고리 · 테마 지도"
            question="어디에 관심이 몰려 있고, 어디가 뜨거워지고 있나?"
            note={`큰 칸 = 카테고리, 안쪽 칸 = 테마. 한 기사가 테마 여러 개에 걸치면 각 테마에 한 번씩 셉니다. 모멘텀 z = (이번 − ${unit} 평균) ÷ 표준편차(최소 1).`}
          >
            <CategoryTreemap radar={radar} view={view} />
          </Panel>

          <div className="grid gap-5 2xl:grid-cols-2">
            <Panel
              id="matrix"
              title="테마 포지셔닝"
              question="지금 대응할 테마와 선점할 테마는?"
              note="가로 = 언급량(로그), 세로 = 모멘텀. 원 크기 = 출처 수, 색 = 신호 단계. 기준선: 언급량 중앙값, +1σ."
            >
              <PositioningMatrix radar={radar} view={view} />
            </Panel>
            <Panel id="timing" title="타이밍 히트맵" question="각 테마는 언제 달아올랐나?" note="행마다 그 테마의 최고치를 100%로 칠합니다. 모멘텀이 큰 순.">
              <TimingHeatmap radar={radar} view={view} />
            </Panel>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <Panel id="cloud" title="기술 워드 클라우드" question="이번 기간 많이 말해진 기술은?" note="카드 키워드를 띄어쓰기·대소문자 무시하고 묶었습니다. 2번 이상 언급된 기술만.">
              <TechCloud radar={radar} view={view} />
            </Panel>
            <Panel id="emerging" title="부상 기술 워치리스트" question="새로 등장했거나 빠르게 늘고 있는 기술" note="신규 = 기준 기간에 없던 기술(출처 2곳 이상). 급상승 = +2σ 이상이면서 평균의 1.5배 이상.">
              <EmergingTable radar={radar} view={view} />
            </Panel>
          </div>

          <Panel id="share" title="카테고리 점유율" question="관심의 무게중심은 어디로 옮겨가고 있나?" note="전체 분석 기사 중 카테고리별 비중(Share of Voice). 모든 칸이 같은 세로 눈금을 씁니다.">
            <CategoryShare radar={radar} view={view} />
          </Panel>

          <div className="grid gap-5 xl:grid-cols-2">
            <Panel id="maturity" title="신호 단계" question="연구 단계인가, 시장에 나왔나?" note="논문·오픈소스 비중이 높으면 초기, 뉴스·커뮤니티가 대부분이면 상용·화제 단계입니다. 비중이 줄면 상용화로 이동 중.">
              <MaturityBars radar={radar} view={view} />
            </Panel>
            <Panel id="network" title="기술 융합 네트워크" question="어떤 기술이 함께 이야기되기 시작했나?" note="같은 기사에 함께 나온 기술 쌍. 배수 = 우연히 함께 나올 기대치 대비(lift).">
              <ConvergenceNetwork radar={radar} view={view} />
              <div className="mt-3 border-t pt-3">
                <PairList radar={radar} view={view} />
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </main>
  );
}
