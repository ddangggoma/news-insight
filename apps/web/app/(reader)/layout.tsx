import Link from "next/link";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/reader/site-header";

export default function ReaderLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2">
        본문으로 건너뛰기
      </a>
      <SiteHeader />
      <div id="content" className="flex-1">
        {children}
      </div>
      <footer className="border-t py-6 text-center text-xs text-muted-foreground">
        매일 04:40 KST 후보 동결 · 05:00 KST 발행 · 원문 저작권은 각 매체에 있습니다 ·{" "}
        <Link href="/rss.xml" className="underline-offset-2 hover:underline">
          RSS
        </Link>
      </footer>
    </div>
  );
}
