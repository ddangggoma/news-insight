import Link from "next/link";
import { notFound } from "next/navigation";

import { TaxonomyMap } from "@/components/reader/radar/taxonomy-map";
import { ApiError } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { isRadarKind, RADAR_KINDS } from "@/lib/radar";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { Distribution } from "@/lib/reader-types";

type Props = { params: Promise<{ period: string; key: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params }: Props) {
  const { period, key } = await params;
  return { title: `분류 탐색 ${isRadarKind(period) ? RADAR_KINDS[period] : ""} ${key}` };
}

// Any scheme, any depth, under any node (plan 15-4b): the radar's field/theme views generalised.
export default async function TaxonomyExplorer({ params, searchParams }: Props) {
  const [{ period, key }, sp] = await Promise.all([params, searchParams]);
  if (!isRadarKind(period)) notFound();
  const scheme = param(sp, "scheme") ?? "technology";
  const depth = Number(param(sp, "depth") ?? 1) || 1;
  const root = param(sp, "root");
  let data: Distribution;
  try {
    data = await readerGet<Distribution>("/radar/distribution", { period, key, scheme, depth: String(depth), ...(root ? { root } : {}) }, REVALIDATE.radarOpen);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) notFound();
    throw error;
  }
  const base = `/radar/${period}/${key}/taxonomy`;
  const href = (next: Record<string, string | number | null>) => {
    const query = new URLSearchParams();
    const merged = { scheme, depth: data.depth, root: root ?? null, ...next };
    for (const [k, v] of Object.entries(merged)) if (v !== null && v !== undefined && v !== "") query.set(k, String(v));
    return `${base}?${query}`;
  };
  const current = data.schemes.find((s) => s.key === data.scheme);
  const maxDepth = current?.max_depth ?? 1;
  const hrefFor = Object.fromEntries(
    data.nodes.map((n) => [n.key, data.depth < maxDepth ? href({ root: `${data.scheme}:${n.key}`, depth: data.depth + 1 }) : null]),
  );
  const level = (d: number) => current?.level_names[d - 1] ?? `${d}단계`;
  const totalDelta = data.total - data.previous_total;
  return (
    <main className="mx-auto max-w-[1200px] space-y-5 px-4 py-5 md:px-6">
      <header className="space-y-1">
        <p className="text-sm">
          <Link href={`/radar/${period}/${key}`} className="text-muted-foreground hover:underline">
            ← 기술 레이더 {RADAR_KINDS[period]} {key}
          </Link>
        </p>
        <h1 className="text-2xl font-bold tracking-tight">분류 탐색</h1>
        <p className="text-sm text-muted-foreground">
          체계와 깊이를 골라 이번 기간 카드가 어디에 몰렸는지 봅니다. 면적은 카드 수, 색은 직전 기간 대비 증감입니다. 칸을 누르면 한 단계 아래로 들어갑니다.
        </p>
      </header>
      <nav aria-label="체계" className="flex flex-wrap gap-2">
        {data.schemes.map((s) => (
          <Link key={s.key} href={href({ scheme: s.key, depth: 1, root: null })} aria-current={s.key === data.scheme ? "page" : undefined} className="rounded-full border px-3 py-1 text-sm aria-[current=page]:border-primary aria-[current=page]:bg-primary/10 aria-[current=page]:font-semibold">
            {s.name}
          </Link>
        ))}
      </nav>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">깊이</span>
        {Array.from({ length: maxDepth }, (_, i) => i + 1)
          .filter((d) => !data.root || d > data.root.depth)
          .map((d) => (
            <Link key={d} href={href({ depth: d })} aria-current={d === data.depth ? "page" : undefined} className="rounded-md border px-2 py-0.5 aria-[current=page]:border-primary aria-[current=page]:font-semibold">
              {level(d)}
            </Link>
          ))}
        {data.root ? (
          <span className="ml-2 flex items-center gap-2">
            <span className="text-muted-foreground">기준</span>
            <span className="font-medium">{data.root.label}</span>
            <Link href={href({ root: null, depth: Math.max(1, data.root.depth) })} className="text-xs text-muted-foreground hover:underline">
              기준 해제
            </Link>
          </span>
        ) : null}
        <span className="ml-auto text-muted-foreground tabular-nums">
          카드 {formatNumber(data.total)} ({totalDelta >= 0 ? "+" : ""}
          {formatNumber(totalDelta)})
        </span>
      </div>
      <section className="rounded-xl border bg-card p-3">
        <TaxonomyMap nodes={data.nodes} hrefFor={hrefFor} />
      </section>
      <section aria-labelledby="table-title" className="space-y-2">
        <h2 id="table-title" className="text-sm font-semibold">
          {level(data.depth)}별 카드
        </h2>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">{level(data.depth)}</th>
                <th className="px-3 py-2 text-right font-medium">이번 기간</th>
                <th className="px-3 py-2 text-right font-medium">직전</th>
                <th className="px-3 py-2 text-right font-medium">증감</th>
                <th className="px-3 py-2 text-right font-medium">비중</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.nodes.map((n) => (
                <tr key={n.key}>
                  <td className="px-3 py-2">
                    {hrefFor[n.key] ? (
                      <Link href={hrefFor[n.key] as string} className="hover:underline">
                        {n.label}
                      </Link>
                    ) : (
                      n.label
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(n.count)}</td>
                  <td className="px-3 py-2 text-right text-muted-foreground tabular-nums">{formatNumber(n.previous)}</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${n.delta > 0 ? "text-impact-opportunity" : n.delta < 0 ? "text-impact-risk" : "text-muted-foreground"}`}>
                    {n.delta > 0 ? "+" : ""}
                    {formatNumber(n.delta)}
                  </td>
                  <td className="px-3 py-2 text-right text-muted-foreground tabular-nums">{data.total ? `${Math.round((n.count / data.total) * 100)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
