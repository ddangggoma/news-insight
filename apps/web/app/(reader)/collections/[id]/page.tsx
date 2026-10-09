import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { archiveCollection } from "@/app/(reader)/collections/actions";
import { CollectionRemove } from "@/components/reader/collection-remove";
import { StoryRow } from "@/components/reader/story-row";
import { TeamComments } from "@/components/reader/team-comments";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { teamApi } from "@/lib/dossier-api";
import { formatDateTime } from "@/lib/format";
import { requireUser } from "@/lib/session";
import type { CollectionDetail } from "@/lib/team-types";

export const metadata: Metadata = { title: "공유 모음", robots: { index: false } };

export default async function CollectionPage({ params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id < 1) notFound();
  const collection = await teamApi<CollectionDetail>("GET", `/collections/${id}`).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });
  return (
    <main className="mx-auto max-w-4xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            <Link href="/collections" className="hover:underline">
              공유 모음
            </Link>
          </p>
          <h1 className="text-xl font-semibold">{collection.title}</h1>
          {collection.description ? <p className="mt-1 text-sm text-muted-foreground">{collection.description}</p> : null}
          <p className="mt-1 text-xs text-muted-foreground">
            카드 {collection.items} · {formatDateTime(collection.updated_at)} 수정{collection.created_by ? ` · 만든 사람 ${collection.created_by}` : ""}
          </p>
        </div>
        <form action={archiveCollection.bind(null, id)}>
          <Button type="submit" variant="ghost" size="sm">
            보관
          </Button>
        </form>
      </div>
      <section aria-label="담긴 카드">
        {collection.entries.length ? (
          collection.entries.map((entry) => (
            <div key={entry.item.id} className="flex gap-2">
              <div className="min-w-0 flex-1">
                <StoryRow item={entry.item} />
                {entry.note || entry.added_by ? (
                  <p className="-mt-2 pb-3 text-xs text-muted-foreground">
                    {entry.note ? `메모: ${entry.note} · ` : ""}
                    {entry.added_by ?? ""} · {formatDateTime(entry.added_at)}
                  </p>
                ) : null}
              </div>
              <div className="pt-4">
                <CollectionRemove collectionId={id} itemId={entry.item.id} />
              </div>
            </div>
          ))
        ) : (
          <p className="rounded-md border py-10 text-center text-sm text-muted-foreground">아직 담긴 카드가 없습니다. 카드 상세에서 이 모음에 담으세요.</p>
        )}
      </section>
      <TeamComments kind="collection" targetId={id} title="팀 댓글" />
    </main>
  );
}
