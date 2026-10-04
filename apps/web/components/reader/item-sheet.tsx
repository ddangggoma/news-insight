"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

/** Article opened over the feed; closing goes back so the feed keeps its scroll position. */
export function ItemSheet({ title, children }: { title: string; children: ReactNode }) {
  const router = useRouter();
  return (
    <Sheet defaultOpen onOpenChange={(open) => !open && router.back()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetTitle className="sr-only">{title}</SheetTitle>
        <SheetDescription className="sr-only">기사 상세</SheetDescription>
        <div className="px-5 pt-10 pb-8">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
