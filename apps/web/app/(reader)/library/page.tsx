import type { Metadata } from "next";

import { LibraryView } from "@/components/reader/library-view";

export const metadata: Metadata = { title: "내 서재" };

export default function LibraryPage() {
  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">내 서재</h1>
        <p className="text-sm text-muted-foreground">로그인 없이 쓰는 북마크와 읽음 기록입니다. JSON으로 내보내 다른 기기에서 가져올 수 있습니다.</p>
      </header>
      <LibraryView />
    </main>
  );
}
