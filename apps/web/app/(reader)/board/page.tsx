import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { type BoardClaim, type BoardRow, type BoardView, HORIZON_TEXT, type Horizon, IMPACT_TEXT, type Impact, opportunityShare } from "@/lib/board-types";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "기회·위협 보드", robots: { index: false } };

const DAYS = [7, 30, 90];
const IMPACT_TONE: Record<Impact, string> = {
  opportunity: "text-emerald-700 dark:text-emerald-300",
  risk: "text-rose-700 dark:text-rose-300",
  watch: "text-muted-foreground",
};

function Claim({ claim }: { claim: BoardClaim }) {
  const first = claim.item_ids[0];
  const text = (
    <span className="line-clamp-3">
      {claim.kind !== "roadmap" ? <span className={cn("mr-1 font-medium", claim.kind === "risk" ? IMPACT_TONE.risk : IMPACT_TONE.opportunity)}>{claim.kind === "risk" ? "위험" : "기회"}</span> : null}
      {claim.text}
    </span>
  );
  return (
    <li className="text-xs" title={`${claim.briefing_date} 브리핑`}>
      {first ? (
        <Link href={`/items/${first}`} scroll={false} className="hover:underline">
          {text}
        </Link>
      ) : (
        text
      )}
    </li>
  );
}

function Row({ row }: { row: BoardRow }) {
  const share = opportunityShare(row.counts);
  return (
    <article className="space-y-3 rounded-lg border p-3">
      <header className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-muted-foreground">{row.field_label}</p>
          <h2 className="font-semibold">
            <Link href={`/?theme=${encodeURIComponent(row.key)}&period=30d`} className="hover:underline">
              {row.label}
            </Link>
          </h2>
        </div>
        {row.persona && Object.keys(row.persona.stances).length ? (
          <span className="rounded-full border px-2 py-0.5 text-[11px]">
            역할 판단:{" "}
            {(Object.entries(row.persona.stances) as [Impact, number][]).map(([k, n]) => `${IMPACT_TEXT[k]} ${n}`).join(" · ")}
          </span>
        ) : null}
      </header>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-rose-500/60" role="img" aria-label={`기회 비중 ${share}%`}>
        <div className="bg-emerald-500" style={{ width: `${share}%` }} />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {(["opportunity", "risk", "watch"] as Impact[]).map((impact) => (
          <div key={impact} className="space-y-1">
            <p className={cn("text-xs font-medium", IMPACT_TONE[impact])}>
              {IMPACT_TEXT[impact]} <span className="tabular-nums">{row.counts[impact]}</span>
            </p>
            <ul className="space-y-0.5">
              {row.evidence[impact].map((e) => (
                <li key={e.item_id} className="text-xs">
                  <Link href={`/items/${e.item_id}`} scroll={false} className="line-clamp-1 hover:underline">
                    {e.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {Object.values(row.horizons).some((c) => c.length) || row.claims.length ? (
        <div className="grid gap-2 border-t pt-2 sm:grid-cols-4">
          {(["1y", "3y", "5y"] as Horizon[]).map((h) => (
            <div key={h}>
              <p className="text-[11px] font-medium text-muted-foreground">{HORIZON_TEXT[h]} 안</p>
              <ul className="space-y-1">
                {row.horizons[h].length ? row.horizons[h].map((c, i) => <Claim key={i} claim={c} />) : <li className="text-xs text-muted-foreground">–</li>}
              </ul>
            </div>
          ))}
          <div>
            <p className="text-[11px] font-medium text-muted-foreground">브리핑 기회·위험</p>
            <ul className="space-y-1">
              {row.claims.length ? row.claims.map((c, i) => <Claim key={i} claim={c} />) : <li className="text-xs text-muted-foreground">–</li>}
            </ul>
          </div>
        </div>
      ) : null}
      {row.persona?.headlines.length ? (
        <ul className="space-y-0.5 border-t pt-2 text-xs">
          {row.persona.headlines.map((h) => (
            <li key={h}>· {h}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export default async function BoardPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const days = DAYS.includes(Number(param(sp, "days"))) ? Number(param(sp, "days")) : 30;
  const persona = param(sp, "persona") || undefined;
  const view = await readerGet<BoardView>("/board", { days, persona }, REVALIDATE.feed);
  const chosen = view.personas.find((p) => p.key === view.persona);

  return (
    <main className="mx-auto max-w-6xl space-y-4 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">기회·위협 보드{chosen ? ` · ${chosen.name}` : ""}</h1>
        <p className="text-sm text-muted-foreground">
          최근 {view.days}일 기술 분야별 카드의 영향(기회·위험·관찰)과, 매일 브리핑의 로드맵을 1·3·5년 지평에 놓았습니다. 역할을 고르면 그 역할이 브리핑에서 읽은 판단을 겹쳐 봅니다.
        </p>
      </div>
      <form className="flex flex-wrap items-center gap-2" action="/board">
        <label htmlFor="board-persona" className="text-sm">
          역할
        </label>
        <select id="board-persona" name="persona" defaultValue={view.persona ?? ""} className="h-9 max-w-[16rem] rounded-md border bg-background px-2 text-sm">
          <option value="">전체</option>
          {view.personas.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
        </select>
        <input type="hidden" name="days" value={view.days} />
        <Button type="submit" size="sm" variant="outline">
          보기
        </Button>
        <nav aria-label="기간" className="ml-auto flex rounded-md border p-0.5 text-sm">
          {DAYS.map((d) => (
            <Link key={d} href={`/board?days=${d}${view.persona ? `&persona=${view.persona}` : ""}`} aria-current={view.days === d ? "page" : undefined} className={cn("rounded px-2.5 py-1", view.days === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
              {d}일
            </Link>
          ))}
        </nav>
      </form>
      {view.rows.length ? (
        <div className="space-y-3">
          {view.rows.map((row) => (
            <Row key={row.key} row={row} />
          ))}
        </div>
      ) : (
        <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">이 기간에 영향이 분류된 카드가 없습니다.</p>
      )}
    </main>
  );
}
