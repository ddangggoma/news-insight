import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { EmptyState } from "@/components/console/empty-state";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import type { SignalChain } from "@/lib/types";

export const metadata = { title: "교차 신호" };

const KIND_LABEL: Record<string, string> = { arxiv: "arXiv", doi: "DOI", github: "GitHub" };

function refUrl(chain: SignalChain): string {
  if (chain.kind === "arxiv") return `https://arxiv.org/abs/${chain.value}`;
  if (chain.kind === "doi") return `https://doi.org/${chain.value}`;
  return `https://github.com/${chain.value}`;
}

export default async function SignalsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const days = param(sp, "days") ?? "7";
  const chains = await api.get<SignalChain[]>("/api/admin/signals", { days });
  return (
    <>
      <PageHeader
        title="교차 신호"
        description="같은 논문(arXiv·DOI)이나 저장소(GitHub)를 서로 다른 트랙이 다룬 경우를 잇습니다. 논문 → 오픈소스 → 커뮤니티 → 미디어 순서로 보여 줍니다."
      />
      <FilterBar
        fields={[
          { name: "days", label: "기간", value: days, options: [{ value: "1", label: "최근 1일" }, { value: "7", label: "최근 7일" }, { value: "30", label: "최근 30일" }] },
        ]}
      />
      {chains.length === 0 ? (
        <EmptyState title="아직 교차 신호가 없습니다" description="논문·저장소를 인용한 커뮤니티 글이나 기사가 들어오면 자동으로 연결됩니다." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          {chains.map((chain) => (
            <article key={`${chain.kind}:${chain.value}`} className="rounded-xl border bg-card p-4">
              <div className="flex items-center gap-2 text-xs">
                <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">{KIND_LABEL[chain.kind]}</span>
                <a href={refUrl(chain)} target="_blank" rel="noreferrer" className="truncate font-mono hover:underline">
                  {chain.value}
                </a>
                <span className="ml-auto text-muted-foreground">{chain.items.length}건</span>
              </div>
              <ol className="relative mt-3 space-y-3 border-l pl-5">
                {chain.items.map((item) => (
                  <li key={item.id} className="space-y-1">
                    <span className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-background bg-primary" />
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <TrackBadge track={item.track} />
                      <span className="truncate">{item.source_name}</span>
                      <span className="ml-auto shrink-0">{formatDateTime(item.published_at ?? item.first_seen_at)}</span>
                    </div>
                    <div className="flex items-start gap-2 text-sm">
                      <Link href={`/console/items/${item.id}`} className="min-w-0 flex-1 hover:underline">
                        {item.title_ko ?? item.title}
                      </Link>
                      <a href={item.url} target="_blank" rel="noreferrer" className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground" aria-label="원문">
                        <ExternalLink className="size-3.5" />
                      </a>
                    </div>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
