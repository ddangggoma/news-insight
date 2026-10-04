"use client";

import type { ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Type 1B layout (§9): three columns on wide screens, tabs on narrow ones. All panes stay
// mounted (forceMount) so search engines and screen readers see the same content.
const pane = "min-w-0 data-[state=inactive]:hidden lg:data-[state=inactive]:block";

export function ThreePane({
  nav,
  main,
  aside,
  mainLabel = "브리핑",
}: {
  nav: ReactNode;
  main: ReactNode;
  aside: ReactNode;
  mainLabel?: string;
}) {
  return (
    <Tabs defaultValue="main" className="mx-auto w-full max-w-[1440px] gap-0 px-4 py-4 lg:py-6">
      <TabsList className="mb-4 grid w-full grid-cols-3 lg:hidden">
        <TabsTrigger value="nav">탐색</TabsTrigger>
        <TabsTrigger value="main">{mainLabel}</TabsTrigger>
        <TabsTrigger value="aside">인사이트</TabsTrigger>
      </TabsList>
      <div className="lg:grid lg:grid-cols-[220px_minmax(0,1fr)_340px] lg:gap-6 xl:grid-cols-[240px_minmax(0,1fr)_380px]">
        <TabsContent value="nav" forceMount className={`${pane} lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-1`}>
          {nav}
        </TabsContent>
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
