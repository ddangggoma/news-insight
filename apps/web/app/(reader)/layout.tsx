import { type ReactNode, Suspense } from "react";

import { BottomNav } from "@/components/reader/bottom-nav";
import { ReaderHeader } from "@/components/reader/reader-header";

export default function ReaderLayout({ children, sheet }: { children: ReactNode; sheet: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Suspense>
        <ReaderHeader />
      </Suspense>
      <div className="pb-16 md:pb-0">{children}</div>
      {sheet}
      <BottomNav />
    </div>
  );
}
