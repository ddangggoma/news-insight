"use client";

import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { uncollect } from "@/app/(reader)/collections/actions";

export function CollectionRemove({ collectionId, itemId }: { collectionId: number; itemId: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button
      type="button"
      aria-label="모음에서 빼기"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          await uncollect(collectionId, itemId);
          router.refresh();
        })
      }
      className="text-muted-foreground hover:text-destructive"
    >
      <X className="size-4" aria-hidden />
    </button>
  );
}
