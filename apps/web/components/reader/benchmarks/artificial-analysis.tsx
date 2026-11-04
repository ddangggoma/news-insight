"use client";

import { Bar, BarChart, CartesianGrid, Cell, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { ProviderLegend, TipBox } from "@/components/reader/benchmarks/parts";
import { PROVIDER_CHART_CONFIG, providerPaint } from "@/components/reader/benchmarks/provider-colors";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import type { AaModel } from "@/lib/benchmark-view";

const TOP = 20;

function Tip({ active, payload }: { active?: boolean; payload?: { payload: AaModel }[] }) {
  const m = payload?.[0]?.payload;
  if (!active || !m?.model) return null;
  return (
    <TipBox
      title={m.model}
      provider={m.provider}
      org={m.org}
      lines={[
        ["지능 지수", m.intelligence === null ? "—" : m.intelligence.toFixed(1)],
        ["가격(100만 토큰, 3:1)", m.price === null ? "—" : `$${m.price.toFixed(2)}`],
        ["출력 속도", m.speed === null ? "—" : `${m.speed.toFixed(0)} 토큰/초`],
      ]}
    />
  );
}

/** Ranked horizontal bars, provider-coloured, the value written at the bar's end. */
function RankedBars({ data, dataKey, format, label }: { data: AaModel[]; dataKey: "intelligence" | "speed"; format: (v: number) => string; label: string }) {
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs font-medium">{label}</figcaption>
      <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto w-full" style={{ height: Math.max(120, data.length * 22 + 16) }}>
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 40, top: 4, bottom: 4 }} barCategoryGap={3} accessibilityLayer>
          <CartesianGrid horizontal={false} strokeOpacity={0.5} />
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="model"
            width={150}
            interval={0}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: string) => (v.length > 24 ? `${v.slice(0, 23)}…` : v)}
          />
          <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<Tip />} />
          <Bar dataKey={dataKey} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((m) => (
              <Cell key={m.model} fill={providerPaint(m.provider).fill} />
            ))}
            <LabelList dataKey={dataKey} position="right" offset={6} className="fill-foreground text-[11px]" formatter={(v: unknown) => (typeof v === "number" ? format(v) : "")} />
          </Bar>
        </BarChart>
      </ChartContainer>
    </figure>
  );
}

/**
 * Artificial Analysis's headline charts: the Intelligence Index (top 20, bars coloured by
 * provider), intelligence against blended price, and output speed of the same models. Every
 * tier of their API requires the credit line, so it is part of the component.
 */
export function ArtificialAnalysisCharts({ models, sourceUrl, attribution }: { models: AaModel[]; sourceUrl: string; attribution: string }) {
  const top = models
    .filter((m) => m.intelligence !== null)
    .sort((a, b) => (b.intelligence ?? 0) - (a.intelligence ?? 0))
    .slice(0, TOP);
  const priced = models.filter((m) => m.intelligence !== null && m.price !== null && m.price > 0);
  const speed = top.filter((m) => m.speed !== null).sort((a, b) => (b.speed ?? 0) - (a.speed ?? 0));
  const labelled = new Set(top.slice(0, 5).map((m) => m.model));

  return (
    <div className="space-y-5">
      <RankedBars data={top} dataKey="intelligence" format={(v) => v.toFixed(1)} label={`Artificial Analysis 지능 지수 (상위 ${top.length})`} />

      <div className="grid gap-5 lg:grid-cols-2">
        <figure className="space-y-1">
          <figcaption className="text-xs font-medium">지능 지수 대 가격 (100만 토큰, 입력 3 : 출력 1 혼합, 로그 눈금)</figcaption>
          <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto h-72 w-full">
            <ScatterChart margin={{ top: 12, right: 16, bottom: 4, left: 0 }} accessibilityLayer>
              <CartesianGrid strokeOpacity={0.5} />
              <XAxis type="number" dataKey="price" scale="log" domain={["auto", "auto"]} tickLine={false} axisLine={false} tickFormatter={(v: number) => `$${v}`} />
              <YAxis type="number" dataKey="intelligence" domain={[0, "auto"]} tickLine={false} axisLine={false} width={32} />
              <ChartTooltip cursor={{ strokeDasharray: "3 3" }} content={<Tip />} />
              <Scatter
                data={priced.map((m) => ({ ...m, tag: labelled.has(m.model) ? m.model : "" }))}
                isAnimationActive={false}
                shape={(props: { cx?: number; cy?: number; payload?: AaModel }) => (
                  <circle cx={props.cx} cy={props.cy} r={5} strokeWidth={2} {...providerPaint(props.payload?.provider ?? "other")} />
                )}
              >
                <LabelList dataKey="tag" position="top" offset={8} className="fill-foreground text-[10px]" />
              </Scatter>
            </ScatterChart>
          </ChartContainer>
          <p className="text-[11px] text-muted-foreground">왼쪽 위일수록 싸고 똑똑한 모델</p>
        </figure>
        <RankedBars data={speed} dataKey="speed" format={(v) => v.toFixed(0)} label="출력 속도 (토큰/초, 중앙값) · 위 모델들" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <ProviderLegend providers={top.map((m) => m.provider)} />
        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          {attribution || "Data: Artificial Analysis"}
        </a>
      </div>
    </div>
  );
}
