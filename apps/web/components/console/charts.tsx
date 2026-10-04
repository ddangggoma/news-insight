"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { Overview } from "@/lib/types";

const stageConfig = { count: { label: "소스 수", color: "var(--chart-1)" } } satisfies ChartConfig;

export function StageChart({ stages }: { stages: Overview["stages"] }) {
  const data = stages.map((stage) => ({ stage: stage.stage === "unverified" ? "미검증" : stage.stage, count: stage.count }));
  return (
    <ChartContainer config={stageConfig} className="h-56 w-full">
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="stage" tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={36} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="count" fill="var(--color-count)" radius={4} />
      </BarChart>
    </ChartContainer>
  );
}

export function HealthBar({ health }: { health: Overview["health"] }) {
  const segments = [
    { key: "success", label: "성공", value: health.success, className: "bg-chart-2" },
    { key: "not_modified", label: "변경 없음", value: health.not_modified, className: "bg-chart-3" },
    { key: "failed", label: "재시도", value: health.failed, className: "bg-chart-4" },
    { key: "dead_lettered", label: "DLQ", value: health.dead_lettered, className: "bg-destructive" },
  ];
  const total = Math.max(1, segments.reduce((sum, segment) => sum + segment.value, 0));
  return (
    <div className="space-y-2">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
        {segments.map((segment) => (
          <div key={segment.key} className={segment.className} style={{ width: `${(segment.value / total) * 100}%` }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {segments.map((segment) => (
          <span key={segment.key} className="flex items-center gap-1.5">
            <span className={`size-2 rounded-full ${segment.className}`} /> {segment.label} {segment.value}
          </span>
        ))}
      </div>
    </div>
  );
}
