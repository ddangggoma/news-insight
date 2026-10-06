import { Clock } from "lucide-react";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { periodic } from "@/lib/briefings";

export const metadata: Metadata = { title: "월간 브리핑" };
// Rendered per request (data still comes from the reader cache): the build has no API key.
export const dynamic = "force-dynamic";

export default async function LatestMonthlyPage() {
  const period = await periodic.latest("month");
  if (period) redirect(`/briefings/monthly/${period.key}`);
  return (
    <main className="mx-auto max-w-3xl space-y-3 px-4 py-10 md:px-6">
      <h1 className="text-2xl font-bold">월간 브리핑</h1>
      <p className="flex items-start gap-2 rounded-lg border bg-muted/40 p-4 text-sm text-muted-foreground">
        <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
        매월 첫 일일 브리핑 직후, 지난달 일일 브리핑을 묶어 발행합니다. 아직 발행된 월간 브리핑이 없습니다.
      </p>
    </main>
  );
}
