import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEAL_KIND_LABEL, type DealKind, type DealView, formatUsd } from "@/lib/deal-types";
import { formatDay } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "투자·제휴", robots: { index: false } };

const DAYS = [30, 90, 180, 365];

function href(query: { days: number; kind?: string; company?: string }): string {
  const params = new URLSearchParams({ days: String(query.days) });
  if (query.kind) params.set("kind", query.kind);
  if (query.company) params.set("company", query.company);
  return `/deals?${params.toString()}`;
}

function PartyLink({ name, companyKey, days }: { name: string; companyKey: string | null; days: number }) {
  return companyKey ? (
    <Link href={href({ days, company: companyKey })} className="font-medium hover:underline">
      {name}
    </Link>
  ) : (
    <span>{name}</span>
  );
}

export default async function DealsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const days = DAYS.includes(Number(param(sp, "days"))) ? Number(param(sp, "days")) : 90;
  const kindParam = param(sp, "kind");
  const kind = kindParam && kindParam in DEAL_KIND_LABEL ? (kindParam as DealKind) : undefined;
  const company = param(sp, "company") ?? undefined;
  const view = await readerGet<DealView>("/deals", { days, kind, company }, REVALIDATE.feed);
  const companyName = company ? view.parties.find((p) => p.key === company)?.name ?? company : null;

  return (
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">투자·제휴{companyName ? ` · ${companyName}` : ""}</h1>
          <p className="text-sm text-muted-foreground">
            카드에서 로컬 모델이 밤마다 뽑은 투자·인수·제휴·상장·합작·라이선스입니다. 금액의 달러 환산은 고정 환율에 따른 어림값입니다.
          </p>
        </div>
        <nav aria-label="기간" className="flex rounded-md border p-0.5 text-sm">
          {DAYS.map((d) => (
            <Link key={d} href={href({ days: d, kind, company })} aria-current={days === d ? "page" : undefined} className={cn("rounded px-2.5 py-1", days === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
              {d === 365 ? "1년" : `${d}일`}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="유형">
        <Link href={href({ days, company })} className={cn("rounded-full border px-3 py-1 text-sm", !kind && "border-primary bg-primary/10")}>
          전체 {kind ? "" : view.total}
        </Link>
        {(Object.keys(DEAL_KIND_LABEL) as DealKind[]).map((k) => {
          const count = view.kinds.find((c) => c.kind === k);
          return (
            <Link key={k} href={href({ days, kind: k, company })} aria-current={kind === k ? "page" : undefined} className={cn("rounded-full border px-3 py-1 text-sm", kind === k && "border-primary bg-primary/10")}>
              {DEAL_KIND_LABEL[k]} {count ? count.count : 0}
              {count?.usd ? <span className="ml-1 text-xs text-muted-foreground">{formatUsd(count.usd)}</span> : null}
            </Link>
          );
        })}
        {company ? (
          <Link href={href({ days, kind })} className="rounded-full border border-dashed px-3 py-1 text-sm text-muted-foreground">
            기업 필터 해제
          </Link>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-base">활발한 기업</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {view.parties.length ? (
              <ul className="space-y-1 text-sm">
                {view.parties.map((p) => (
                  <li key={p.key ?? p.name} className="flex items-baseline justify-between gap-2">
                    <PartyLink name={p.name} companyKey={p.key} days={days} />
                    <span className="text-xs text-muted-foreground">
                      {Object.entries(p.kinds)
                        .map(([k, n]) => `${DEAL_KIND_LABEL[k as DealKind]} ${n}`)
                        .join(" · ")}
                      {p.usd ? ` · ${formatUsd(p.usd)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">아직 추출된 거래가 없습니다.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-base">기업 간 관계</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {view.pairs.length ? (
              <ul className="space-y-1 text-sm">
                {view.pairs.map((p) => (
                  <li key={`${p.actor}-${p.counterparty}`} className="flex flex-wrap items-baseline gap-1">
                    <PartyLink name={p.actor} companyKey={p.actor_key} days={days} />
                    <span className="text-muted-foreground">→</span>
                    <PartyLink name={p.counterparty} companyKey={p.counterparty_key} days={days} />
                    <span className="ml-auto text-xs text-muted-foreground">
                      {p.kinds.map((k) => DEAL_KIND_LABEL[k]).join("·")} {p.count > 1 ? `${p.count}건` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">상대가 밝혀진 거래가 아직 없습니다.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <section aria-labelledby="deal-list" className="space-y-2">
        <h2 id="deal-list" className="text-base font-semibold">
          거래 ({view.total}건{view.total > view.deals.length ? `, 최근 ${view.deals.length}건 표시` : ""})
        </h2>
        {view.deals.length ? (
          <ul className="divide-y rounded-md border">
            {view.deals.map((d) => (
              <li key={d.id} className="space-y-0.5 p-3 text-sm">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="rounded border px-1.5 text-[11px]">{DEAL_KIND_LABEL[d.kind]}</span>
                  <PartyLink name={d.actor} companyKey={d.actor_key} days={days} />
                  {d.counterparty ? (
                    <>
                      <span className="text-muted-foreground">→</span>
                      <PartyLink name={d.counterparty} companyKey={d.counterparty_key} days={days} />
                    </>
                  ) : null}
                  {d.stage ? <span className="text-xs text-muted-foreground">{d.stage}</span> : null}
                  {d.amount_usd ? <span className="text-xs font-medium">{formatUsd(d.amount_usd)}</span> : null}
                  <span className="ml-auto text-xs text-muted-foreground">{d.announced_on ? formatDay(d.announced_on) : ""}</span>
                </div>
                <p>{d.summary}</p>
                <p className="text-xs text-muted-foreground">
                  근거:{" "}
                  <Link href={`/items/${d.item_id}`} scroll={false} className="hover:underline">
                    {d.title}
                  </Link>{" "}
                  · {d.source}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-md border py-10 text-center text-sm text-muted-foreground">
            해당 조건의 거래가 없습니다. 추출은 매일 밤 00~06시에 로컬 모델이 진행합니다.
          </p>
        )}
      </section>
    </main>
  );
}
