import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { KIND_LABEL, WatchAdd, WatchRemove, WatchSuggest } from "@/components/console/watch-forms";
import { api } from "@/lib/api";
import type { WatchPage } from "@/lib/types";

export const metadata = { title: "관심 목록" };

export default async function WatchlistPage() {
  const page = await api.get<WatchPage>("/api/admin/watchlist");
  return (
    <>
      <PageHeader
        title="관심 목록"
        description="여기 넣은 기업·테마·기술 키워드는 매일 브리핑 맨 위 '내 관심 항목'에 그날 보도 수와 대표 기사로 나옵니다. 메일·푸시 알림은 보내지 않습니다."
      />
      <section className="space-y-3">
        <WatchAdd companies={page.companies} />
        {page.items.length ? (
          <ul className="divide-y rounded-lg border">
            {page.items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 p-3">
                <span className="w-20 shrink-0 text-xs text-muted-foreground">{KIND_LABEL[item.kind]}</span>
                <span className="min-w-0 flex-1 font-medium">{item.label}</span>
                <span className="font-mono text-xs text-muted-foreground">{item.key}</span>
                <WatchRemove item={item} />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="관심 항목이 없습니다" description="아래 추천에서 고르거나 위에서 추가하세요." />
        )}
      </section>
      {page.suggestions.length ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">
            추천 <span className="font-normal text-muted-foreground">최근 7일 DX 관련 보도가 많은 기업·테마</span>
          </h2>
          <div className="flex flex-wrap gap-2">
            {page.suggestions.map((s) => (
              <WatchSuggest key={`${s.kind}-${s.key}`} suggestion={s} />
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
