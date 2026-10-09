import type { Metadata } from "next";
import Link from "next/link";

import { Sparkline } from "@/components/reader/sparkline";
import { type AreaMaturity, type MaturityView, movement, type Stage, STAGE_HINT, STAGE_LABEL } from "@/lib/maturity-types";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "성숙도·로드맵", robots: { index: false } };

const STAGES: Stage[] = ["research", "organising", "product", "diffusion"];

function MixBar({ mix }: { mix: AreaMaturity["mix"] }) {
  const tone: Record<Stage, string> = { research: "bg-sky-500", organising: "bg-violet-500", product: "bg-emerald-500", diffusion: "bg-amber-500" };
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-label={STAGES.map((s) => `${STAGE_LABEL[s]} ${Math.round(mix[s] * 100)}%`).join(", ")} role="img">
      {STAGES.map((s) => (
        <div key={s} className={tone[s]} style={{ width: `${mix[s] * 100}%` }} />
      ))}
    </div>
  );
}

function AreaCard({ area }: { area: AreaMaturity }) {
  const move = movement(area.history);
  const values = area.history.map((h) => h.index ?? 0);
  return (
    <li className="space-y-1.5 rounded-md border bg-background p-2.5">
      <div className="flex items-start gap-2">
        <Link href={`/?theme=${encodeURIComponent(area.key)}&period=30d`} className="min-w-0 flex-1 text-sm font-medium hover:underline">
          {area.label}
        </Link>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground" title="성숙도 지수 (1 연구 ~ 4 확산)">
          {area.index.toFixed(1)}
          {move ? <span className={cn("ml-1", move.startsWith("+") ? "text-emerald-600" : "text-rose-600")}>{move}</span> : null}
        </span>
      </div>
      <MixBar mix={area.mix} />
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>
          {area.field_label} · 카드 {area.count}
        </span>
        <span className="ml-auto">
          <Sparkline values={values} width={48} height={14} label={`${area.label} 성숙도 추이`} />
        </span>
      </div>
      {area.companies.length ? <p className="line-clamp-1 text-[11px]">{area.companies.map((c) => c.label).join(" · ")}</p> : null}
    </li>
  );
}

export default async function RoadmapPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const field = param(sp, "field") ?? undefined;
  const view = await readerGet<MaturityView>("/maturity", { field }, REVALIDATE.feed);
  const all = field ? await readerGet<MaturityView>("/maturity", {}, REVALIDATE.feed) : view;

  return (
    <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">성숙도·로드맵</h1>
        <p className="text-sm text-muted-foreground">
          최근 {view.days}일 카드의 신호 구성으로 기술 분야마다 단계를 읽습니다. 지수는 1(연구)~4(확산)이고, 옆 숫자는 최근 몇 달 사이의 변화입니다. 연구 출처가 많은 분야는 연구 쪽으로 기울 수 있습니다.
        </p>
      </div>
      <nav aria-label="분야" className="flex flex-wrap gap-1.5">
        <Link href="/roadmap" aria-current={!field ? "page" : undefined} className={cn("rounded-full border px-3 py-1 text-sm", !field && "border-primary bg-primary/10")}>
          전체
        </Link>
        {all.fields.map((f) => (
          <Link key={f.key} href={`/roadmap?field=${encodeURIComponent(f.key)}`} aria-current={field === f.key ? "page" : undefined} className={cn("rounded-full border px-3 py-1 text-sm", field === f.key && "border-primary bg-primary/10")}>
            {f.label}
          </Link>
        ))}
      </nav>
      {view.areas.length ? (
        <div className="grid gap-3 md:grid-cols-4">
          {STAGES.map((stage) => {
            const areas = view.areas.filter((a) => a.stage === stage);
            return (
              <section key={stage} aria-labelledby={`stage-${stage}`} className="space-y-2 rounded-lg bg-muted/40 p-2.5">
                <h2 id={`stage-${stage}`} className="text-sm font-semibold">
                  {STAGE_LABEL[stage]} <span className="font-normal text-muted-foreground">{areas.length}</span>
                </h2>
                <p className="text-[11px] text-muted-foreground">{STAGE_HINT[stage]}</p>
                <ul className="space-y-2">
                  {areas.map((area) => (
                    <AreaCard key={area.key} area={area} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      ) : (
        <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">단계를 읽을 만큼 카드가 쌓인 분야가 없습니다.</p>
      )}
    </main>
  );
}
