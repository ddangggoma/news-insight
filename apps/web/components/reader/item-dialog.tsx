"use client";

import { ExternalLink, Maximize2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { DetailDialog, DialogAction } from "@/components/detail-dialog";

/** Article opened over the page; closing goes back so the page keeps its scroll position. */
export function ItemDialog({ id, url, title, children }: { id: number; url: string; title: string; children: ReactNode }) {
  const router = useRouter();
  const [open, setOpen] = useState(true);
  return (
    <DetailDialog
      open={open}
      onOpenChange={(next) => {
        if (next) return;
        setOpen(false);
        // let the exit animation play before the route changes
        window.setTimeout(() => router.back(), 140);
      }}
      title={title}
      label="기사 상세"
      description="기사 요약, 분류, 관련 보도"
      actions={
        <>
          <DialogAction href={`/items/${id}`} external icon={<Maximize2 className="size-4" aria-hidden />}>
            새 탭
          </DialogAction>
          <DialogAction href={url} external icon={<ExternalLink className="size-4" aria-hidden />}>
            원문
          </DialogAction>
        </>
      }
    >
      <div className="px-5 py-6 md:px-8 md:py-7">{children}</div>
    </DetailDialog>
  );
}
