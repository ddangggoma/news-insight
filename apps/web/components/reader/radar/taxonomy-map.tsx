"use client";

import { useRouter } from "next/navigation";
import { ResponsiveContainer, Tooltip, Treemap } from "recharts";

import type { DistributionNode } from "@/lib/reader-types";

type Cell = DistributionNode & { name: string; size: number; href: string | null; [key: string]: unknown };

function tone(delta: number, count: number): string {
  if (!count) return "var(--muted)";
  const share = Math.min(1, Math.abs(delta) / Math.max(count, 1));
  if (delta > 0) return `color-mix(in oklab, var(--impact-opportunity) ${Math.round(25 + share * 55)}%, var(--card))`;
  if (delta < 0) return `color-mix(in oklab, var(--impact-risk) ${Math.round(20 + share * 45)}%, var(--card))`;
  return "color-mix(in oklab, var(--muted-foreground) 18%, var(--card))";
}

function Content(props: { x?: number; y?: number; width?: number; height?: number; payload?: Cell; name?: string; count?: number; delta?: number; href?: string | null }) {
  const { x = 0, y = 0, width = 0, height = 0, name = "", count = 0, delta = 0, href } = props;
  return (
    <g style={{ cursor: href ? "pointer" : "default" }}>
      <rect x={x} y={y} width={width} height={height} rx={6} fill={tone(delta, count)} stroke="var(--background)" strokeWidth={2} />
      {width > 70 && height > 34 ? (
        <>
          <text x={x + 8} y={y + 18} fontSize={12} fontWeight={600} fill="var(--foreground)">
            {name.length > Math.floor(width / 12) ? `${name.slice(0, Math.max(3, Math.floor(width / 12) - 1))}…` : name}
          </text>
          <text x={x + 8} y={y + 33} fontSize={11} fill="var(--muted-foreground)">
            {count} {delta > 0 ? `▲${delta}` : delta < 0 ? `▼${-delta}` : ""}
          </text>
        </>
      ) : null}
    </g>
  );
}

/** Area = cards this period, colour = change against the period before; click to go deeper. */
export function TaxonomyMap({ nodes, hrefFor }: { nodes: DistributionNode[]; hrefFor: Record<string, string | null> }) {
  const router = useRouter();
  const data: Cell[] = nodes.filter((n) => n.count > 0).map((n) => ({ ...n, name: n.label, size: n.count, href: hrefFor[n.key] ?? null }));
  if (!data.length) return <p className="py-10 text-center text-sm text-muted-foreground">이 기간에 분류된 카드가 없습니다.</p>;
  return (
    <div className="h-[420px] w-full min-w-0" role="img" aria-label="분류 분포 트리맵">
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          dataKey="size"
          isAnimationActive={false}
          content={<Content />}
          onClick={(cell: unknown) => {
            const href = (cell as { href?: string | null }).href;
            if (href) router.push(href);
          }}
        >
          <Tooltip
            formatter={(_value, _name, item) => {
              const cell = (item as { payload?: Cell }).payload;
              return cell ? [`${cell.count}건 (직전 ${cell.previous}, ${cell.delta >= 0 ? "+" : ""}${cell.delta})`, cell.label] : ["", ""];
            }}
          />
        </Treemap>
      </ResponsiveContainer>
    </div>
  );
}
