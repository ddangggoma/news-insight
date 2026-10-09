import type { Metadata } from "next";

import { AskPanel } from "@/components/reader/ask-panel";
import { scopeOptions } from "@/lib/scope-options";
import { requireUser } from "@/lib/session";
import { loadTaxonomy } from "@/lib/taxonomy-server";

export const metadata: Metadata = { title: "질문하기", robots: { index: false } };

export default async function AskPage() {
  await requireUser();
  const scopes = scopeOptions(await loadTaxonomy());
  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">질문하기</h1>
        <p className="text-sm text-muted-foreground">
          수집·카드화된 기사만 근거로 로컬 모델이 답합니다. 답의 [번호]는 아래 근거 기사로 이어집니다.
        </p>
      </div>
      <AskPanel scopes={scopes} />
    </main>
  );
}
