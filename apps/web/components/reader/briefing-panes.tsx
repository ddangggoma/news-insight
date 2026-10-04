"use client";

import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// §9 briefing layout: briefing and insights side by side on wide screens, tabs on narrow ones.
// Both panes stay mounted (forceMount) so screen readers and search see the same content.
const pane = "min-w-0 data-[state=inactive]:hidden lg:data-[state=inactive]:block";

export function BriefingPanes({ main, aside }: { main: ReactNode; aside: ReactNode }) {
  return (
    <Tabs defaultValue="main" className="mx-auto w-full max-w-[1280px] gap-0 px-4 py-4 md:px-6 lg:py-6">
      <TabsList className="mb-4 grid w-full grid-cols-2 lg:hidden">
        <TabsTrigger value="main">브리핑</TabsTrigger>
        <TabsTrigger value="aside">인사이트</TabsTrigger>
      </TabsList>
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8 xl:grid-cols-[minmax(0,1fr)_400px]">
        <TabsContent value="main" forceMount className={pane}>
          {main}
        </TabsContent>
        <TabsContent value="aside" forceMount className={pane}>
          {aside}
        </TabsContent>
      </div>
    </Tabs>
  );
}
