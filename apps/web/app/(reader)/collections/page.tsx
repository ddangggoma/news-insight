import type { Metadata } from "next";
import Link from "next/link";

import { createCollection } from "@/app/(reader)/collections/actions";
import { Button } from "@/components/ui/button";
import { teamApi } from "@/lib/dossier-api";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { requireUser } from "@/lib/session";
import type { CollectionSummary } from "@/lib/team-types";

export const metadata: Metadata = { title: "공유 모음", robots: { index: false } };

export default async function CollectionsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const collections = await teamApi<CollectionSummary[]>("GET", "/collections");
  return (
    <main className="mx-auto max-w-4xl space-y-4 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">공유 모음</h1>
        <p className="text-sm text-muted-foreground">보고서·질문을 위해 팀이 손으로 모은 카드입니다. 카드 상세에서 "모음에 담기"로 넣고, 메모로 이유를 남깁니다.</p>
      </div>
      <form action={createCollection} className="flex flex-wrap gap-2 rounded-md border p-3">
        <label htmlFor="collection-title" className="sr-only">
          새 모음 이름
        </label>
        <input id="collection-title" name="title" required minLength={2} maxLength={120} placeholder="새 모음 이름 (예: 4분기 경영 보고 근거)" className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm" />
        <input name="description" maxLength={2000} placeholder="설명 (선택)" aria-label="설명" className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm" />
        <Button type="submit" size="sm">
          만들기
        </Button>
        {param(sp, "error") ? <p role="alert" className="w-full text-xs text-destructive">이름을 두 글자 이상 입력하세요.</p> : null}
      </form>
      {collections.length ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {collections.map((c) => (
            <li key={c.id}>
              <Link href={`/collections/${c.id}`} className="block h-full rounded-md border p-4 hover:border-primary">
                <h2 className="font-semibold">{c.title}</h2>
                {c.description ? <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{c.description}</p> : null}
                <p className="mt-2 text-xs text-muted-foreground">
                  카드 {c.items} · 댓글 {c.comments} · {formatDateTime(c.updated_at)}
                  {c.created_by ? ` · ${c.created_by}` : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">아직 모음이 없습니다.</p>
      )}
    </main>
  );
}
