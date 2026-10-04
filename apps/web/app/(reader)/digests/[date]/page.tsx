import Link from "next/link";
import { notFound } from "next/navigation";

import { DigestView } from "@/components/console/digest-view";
import { ApiError } from "@/lib/api";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { PublicDigest } from "@/lib/reader-types";

async function load(date: string): Promise<PublicDigest> {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) notFound();
  try {
    return await readerGet<PublicDigest>(`/digests/${date}`, {}, REVALIDATE.digest);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }) {
  const digest = await load((await params).date);
  return { title: `${digest.digest_date} 다이제스트`, description: digest.content.headline };
}

export default async function DigestPage({ params }: { params: Promise<{ date: string }> }) {
  const digest = await load((await params).date);
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 md:px-6">
      <Link href="/digests" className="text-sm text-muted-foreground hover:underline">
        ← 다이제스트 목록
      </Link>
      <DigestView digest={{ ...digest, model: null, cost_usd: null, error: null }} />
    </main>
  );
}
