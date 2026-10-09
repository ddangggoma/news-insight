import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { dossierApi } from "@/lib/dossier-api";
import type { DossierSummary } from "@/lib/dossier-types";
import { formatDateTime } from "@/lib/format";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "주제 파일", robots: { index: false } };

export default async function DossiersPage() {
  await requireUser();
  const dossiers = await dossierApi<DossierSummary[]>("GET", "");
  return (
    <main className="mx-auto max-w-4xl space-y-4 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">주제 파일</h1>
          <p className="text-sm text-muted-foreground">팀이 함께 추적하는 주제입니다. 조건에 맞는 카드가 자동으로 모이고, 가설에 근거를 붙여 판단을 쌓습니다.</p>
        </div>
        <Button asChild size="sm">
          <Link href="/dossiers/new">
            <Plus className="size-4" aria-hidden />새 주제 파일
          </Link>
        </Button>
      </div>
      {dossiers.length ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {dossiers.map((d) => (
            <li key={d.id}>
              <Link href={`/dossiers/${d.id}`} className="block h-full rounded-md border p-4 hover:border-primary">
                <h2 className="font-semibold">{d.title}</h2>
                {d.description ? <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{d.description}</p> : null}
                <p className="mt-2 text-xs text-muted-foreground">
                  최근 7일 <strong className="text-foreground tabular-nums">{d.recent}</strong>건 · 90일 {d.total}건 · 가설 {d.hypotheses}개
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDateTime(d.updated_at)}
                  {d.updated_by ? ` · ${d.updated_by}` : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded-md border py-16 text-center">
          <p className="font-semibold">아직 주제 파일이 없습니다</p>
          <p className="mt-1 text-sm text-muted-foreground">추적할 주제를 만들면 관련 카드·타임라인·기업·수치가 모입니다.</p>
        </div>
      )}
    </main>
  );
}
