import { type ReactNode, Suspense } from "react";

import { BottomNav } from "@/components/reader/bottom-nav";
import { ReaderHeader } from "@/components/reader/reader-header";
import { requireUser } from "@/lib/session";

export default async function ReaderLayout({ children, sheet }: { children: ReactNode; sheet: ReactNode }) {
  const user = await requireUser();
  return (
    <div className="min-h-screen bg-background">
      <Suspense>
        <ReaderHeader user={{ name: user.name, admin: user.role === "admin" }} />
      </Suspense>
      <div className="pb-16 md:pb-0">{children}</div>
      {sheet}
      <BottomNav />
    </div>
  );
}
