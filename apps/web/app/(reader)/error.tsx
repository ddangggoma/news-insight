"use client";

import { Button } from "@/components/ui/button";

export default function ReaderError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto max-w-xl px-4 py-20 text-center">
      <h1 className="text-lg font-semibold">기사를 불러오지 못했습니다</h1>
      <p className="mt-2 text-sm text-muted-foreground">잠시 뒤 다시 시도해 주세요. 문제가 계속되면 관리자에게 알려 주세요.</p>
      <Button className="mt-6" onClick={reset}>
        다시 시도
      </Button>
    </main>
  );
}
