"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, ToggleChip } from "@/components/reader/benchmarks/parts";
import { slotColor } from "@/components/reader/benchmarks/provider-colors";
import { Button } from "@/components/ui/button";
import { type ChartConfig, ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { LIVEBENCH_CATEGORIES } from "@/lib/benchmark-types";
import type { LiveModel } from "@/lib/benchmark-view";
import { cn } from "@/lib/utils";

type Category = (typeof LIVEBENCH_CATEGORIES)[number]["key"];
const COMPARE_MAX = 4;
const SHADED = 5;

function topValues(models: LiveModel[], read: (m: LiveModel) => number | null | undefined): Set<number> {
  const values = models.map(read).filter((v): v is number => typeof v === "number");
  return new Set(values.sort((a, b) => b - a).slice(0, SHADED));
}

const col = createColumnHelper<LiveModel>();

function buildColumns(top: Record<string, Set<number>>) {
  const shade = (key: string, value: number | null | undefined) => (typeof value === "number" && top[key]?.has(value) ? "bg-primary/10 font-medium" : undefined);
  return [
    col.accessor("model", {
      header: "모델",
      enableHiding: false,
      meta: { label: "모델" },
      cell: ({ row: { original: m } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-6 text-right text-xs text-muted-foreground tabular-nums">{m.rank ?? ""}</span>
          <ProviderDot provider={m.provider} />
          <span className="font-medium" title={m.name !== m.model ? m.model : undefined}>
            {m.name}
          </span>
          {m.open && <span className="rounded border border-emerald-600/40 px-1 text-xs text-emerald-700 dark:text-emerald-400">open</span>}
          {m.rank === null && (
            <span className="rounded bg-muted px-1 text-xs text-muted-foreground" title="LiveBench 기본 순위표에 없는 모델(모델 목록에 없거나 파인튠, 또는 같은 계열의 더 높은 변형이 있음)">
              순위 외
            </span>
          )}
          <ChangeMark change={m.change} by={m.changeBy} />
        </span>
      ),
    }),
    col.accessor((m) => m.org ?? undefined, { id: "org", header: "조직", meta: { label: "조직" }, cell: ({ row }) => row.original.org ?? "—" }),
    // unranked models sort after the ranked ones in either direction (undefined sorts last)
    col.accessor((m) => (m.rank === null ? undefined : (m.overall ?? undefined)), {
      id: "overall",
      header: "종합",
      enableHiding: false,
      meta: { label: "종합", numeric: true, cellClassName: (m) => cn("font-semibold", shade("overall", m.rank === null ? null : m.overall)) },
      cell: ({ row: { original: m } }) =>
        m.overall === null ? "—" : <span className={m.rank === null ? "text-muted-foreground" : undefined}>{m.overall.toFixed(1)}</span>,
    }),
    ...LIVEBENCH_CATEGORIES.map((c) =>
      col.accessor((m) => m.scores[c.key], {
        id: c.key,
        header: c.label,
        meta: { label: c.label, numeric: true, cellClassName: (m) => shade(c.key, m.scores[c.key]) },
        cell: ({ getValue }) => {
          const value = getValue();
          return value === undefined ? <span className="text-muted-foreground">—</span> : value.toFixed(1);
        },
      }),
    ),
    col.accessor((m) => m.costPerSuccess ?? undefined, {
      id: "cost",
      header: "성공 작업당 비용",
      meta: { label: "성공 작업당 비용", numeric: true },
      // cheapest first, as a cost should
      sortDescFirst: false,
      // three decimals, as the site prints it ($7.406)
      cell: ({ row }) => (row.original.costPerSuccess === null ? "—" : `$${row.original.costPerSuccess.toFixed(3)}`),
    }),
  ];
}

function SubScores({ model }: { model: LiveModel }) {
  const cats = LIVEBENCH_CATEGORIES.filter((c) => model.parts[c.key] && Object.keys(model.parts[c.key]!).length > 0);
  return (
    <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
      {cats.map((c) => (
        <div key={c.key}>
          <div className="mb-1 flex items-baseline justify-between font-medium">
            <span>{c.label}</span>
            <span className="tabular-nums">{model.scores[c.key]?.toFixed(1) ?? "—"}</span>
          </div>
          <ul className="space-y-0.5 text-muted-foreground">
            {Object.entries(model.parts[c.key]!).map(([part, value]) => (
              <li key={part} className="flex justify-between gap-2">
                <span className="truncate">{part}</span>
                <span className="tabular-nums text-foreground">{typeof value === "number" ? value.toFixed(1) : "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Up to four picked models side by side, one group of bars per category. */
function Compare({ models, onClear }: { models: LiveModel[]; onClear: () => void }) {
  const config = Object.fromEntries(
    models.map((m, index) => [`m${index}`, { label: m.name, theme: { light: slotColor(index, "light"), dark: slotColor(index, "dark") } }]),
  ) satisfies ChartConfig;
  const data = [{ key: "overall", label: "종합" }, ...LIVEBENCH_CATEGORIES].map((c) => ({
    label: c.label,
    ...Object.fromEntries(models.map((m, index) => [`m${index}`, c.key === "overall" ? m.overall : (m.scores[c.key as Category] ?? null)])),
  }));
  return (
    <section aria-label="모델 비교" className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium">영역별 비교</h3>
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X aria-hidden />
          비교 해제
        </Button>
      </div>
      <ChartContainer config={config} className="aspect-auto h-64 w-full">
        <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }} barGap={2} accessibilityLayer>
          <CartesianGrid vertical={false} strokeOpacity={0.5} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickLine={false} axisLine={false} width={32} />
          <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent className="flex-wrap" />} />
          {models.map((_, index) => (
            <Bar key={index} dataKey={`m${index}`} fill={`var(--color-m${index})`} radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
          ))}
        </BarChart>
      </ChartContainer>
    </section>
  );
}

/**
 * LiveBench's table: overall, the seven category columns in the site's order and cost per
 * successful task; top five of each column shaded; open-weights and organisation filters,
 * a column menu, rows that open into the category's sub-scores, and a pick-up-to-four
 * comparison.
 */
export function LiveBenchTable({ models }: { models: LiveModel[] }) {
  const [openOnly, setOpenOnly] = useState(false);
  const [org, setOrg] = useState("");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const orgs = useMemo(() => [...new Set(models.map((m) => m.org).filter((o): o is string => !!o))].sort(), [models]);
  const shown = models.filter(
    (m) => (!openOnly || m.open) && (!org || m.org === org) && (!query || `${m.name} ${m.model}`.toLowerCase().includes(query.trim().toLowerCase())),
  );
  const top: Record<string, Set<number>> = {
    overall: topValues(shown, (m) => (m.rank === null ? null : m.overall)),
    ...Object.fromEntries(LIVEBENCH_CATEGORIES.map((c) => [c.key, topValues(shown, (m) => m.scores[c.key])])),
  };
  const columns = buildColumns(top);
  const compared = picked.map((id) => models.find((m) => m.model === id)).filter((m): m is LiveModel => !!m);

  return (
    <div className="space-y-3">
      <DataTable
        label="LiveBench 순위표"
        columns={columns}
        data={shown}
        getRowId={(m) => m.model}
        rowName={(m) => m.name}
        initialSorting={[{ id: "overall", desc: true }]}
        initialVisibility={{ org: false }}
        enableColumnVisibility
        enableExpanding
        expandLabel="세부 점수"
        canExpand={(m) => Object.keys(m.parts).length > 0}
        renderSubRow={(m) => <SubScores model={m} />}
        enableRowSelection
        maxSelected={COMPARE_MAX}
        selectLabel="비교에 추가"
        selected={picked}
        onSelectedChange={setPicked}
        toolbar={
          <>
            <Input
              type="search"
              aria-label="모델 검색"
              placeholder="모델 검색"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-7 w-40 text-xs"
            />
            <ToggleChip pressed={openOnly} onClick={() => setOpenOnly((v) => !v)}>
              오픈 웨이트만
            </ToggleChip>
            <select aria-label="조직" value={org} onChange={(event) => setOrg(event.target.value)} className="h-7 rounded-md border bg-background px-2 text-xs">
              <option value="">모든 조직</option>
              {orgs.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">{`비교할 모델을 최대 ${COMPARE_MAX}개 고르세요 (${picked.length}/${COMPARE_MAX})`}</span>
          </>
        }
      />
      {compared.length >= 2 && <Compare models={compared} onClear={() => setPicked([])} />}
      <p className="text-xs text-muted-foreground">
        종합은 사이트와 같이 점수가 있는 영역들의 가중 평균(에이전틱 ×2, 코딩·디자인 ×1.5)이고, 순위는 사이트 기본 순위표와 같습니다(모델 목록에
        없는 모델과 파인튠은 순위 외). 진한 칸은 각 열의 상위 {SHADED}개, 조직과 open 표시는 사이트가 밝힌 정보 그대로입니다.
      </p>
    </div>
  );
}
