"use client";

import { SlidersHorizontal } from "lucide-react";

import { FacetPanel } from "@/components/reader/facet-panel";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { ReaderFilters } from "@/lib/reader-filters";
import type { Facets } from "@/lib/reader-types";

export function FacetSheet({ facets, filters, active }: { facets: Facets; filters: ReaderFilters; active: number }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="rounded-full xl:hidden">
          <SlidersHorizontal className="size-4" aria-hidden />
          필터{active ? ` ${active}` : ""}
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[min(340px,90vw)] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>필터</SheetTitle>
        </SheetHeader>
        <div className="px-4 pb-6">
          <FacetPanel facets={facets} filters={filters} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
