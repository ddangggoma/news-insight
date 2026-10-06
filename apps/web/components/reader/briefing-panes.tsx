"use client";

import type { ReactNode } from "react";

import { BriefingDepth } from "@/components/reader/briefing-depth";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// §9 briefing layout: briefing and insights side by side on wide screens, tabs on narrow ones.
// Both panes stay mounted (forceMount) so screen readers and search see the same content.
// The insights pane (radar signals, personas, strategy) belongs to the deep reading level
// (plan 13 C1): at one and five minutes the briefing takes the whole width.
const pane = "min-w-0 data-[state=inactive]:hidden lg:data-[state=inactive]:block";
// `!`: the tab panes set `lg:data-[state=inactive]:block`, which would otherwise win
const deepOnly = "group-data-[depth=one]/brief:hidden! group-data-[depth=five]/brief:hidden!";

export function BriefingPanes({ main, aside }: { main: ReactNode; aside: ReactNode }) {
  return (
    <BriefingDepth className="mx-auto w-full min-w-0 max-w-[1280px] px-4 py-4 md:px-6 lg:py-6">
      <Tabs defaultValue="main" className="w-full min-w-0 gap-0">
        <TabsList className={`mb-4 grid w-full grid-cols-2 lg:hidden ${deepOnly}`}>
          <TabsTrigger value="main">브리핑</TabsTrigger>
          <TabsTrigger value="aside">인사이트</TabsTrigger>
        </TabsList>
        <div className="mx-auto w-full min-w-0 max-w-3xl lg:gap-8 group-data-[depth=deep]/brief:max-w-none lg:group-data-[depth=deep]/brief:grid lg:group-data-[depth=deep]/brief:grid-cols-[minmax(0,1fr)_360px] xl:group-data-[depth=deep]/brief:grid-cols-[minmax(0,1fr)_400px]">
          <TabsContent value="main" forceMount className={pane}>
            {main}
          </TabsContent>
          <TabsContent value="aside" forceMount className={`${pane} ${deepOnly}`}>
            {aside}
          </TabsContent>
        </div>
      </Tabs>
    </BriefingDepth>
  );
}
