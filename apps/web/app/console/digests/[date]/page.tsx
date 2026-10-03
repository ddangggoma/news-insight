import { notFound } from "next/navigation";

import { DigestView } from "@/components/console/digest-view";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api, ApiError } from "@/lib/api";
import type { DigestOut } from "@/lib/types";

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  return { title: `다이제스트 ${date}` };
}

export default async function DigestPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  let digest: DigestOut;
  try {
    digest = await api.get<DigestOut>(`/api/admin/digests/${encodeURIComponent(date)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  return (
    <>
      {digest.status === "fallback" ? (
        <Alert>
          <AlertTitle>규칙 기반 대체본</AlertTitle>
          <AlertDescription>Claude 요약을 만들지 못했습니다{digest.error ? `: ${digest.error}` : ""}</AlertDescription>
        </Alert>
      ) : null}
      <DigestView digest={digest} />
    </>
  );
}
