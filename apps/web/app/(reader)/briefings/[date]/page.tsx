import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BriefingAside } from "@/components/reader/briefing-aside";
import { BriefingMain } from "@/components/reader/briefing-main";
import { TaxonomyTree } from "@/components/reader/taxonomy-tree";
import { ThreePane } from "@/components/reader/three-pane";
import { formatBriefingDate } from "@/lib/format";
import { reader } from "@/lib/reader";

export const dynamic = "force-dynamic";
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }): Promise<Metadata> {
  const { date } = await params;
  return { title: DAY.test(date) ? `${formatBriefingDate(date)} 브리핑` : "브리핑" };
}

export default async function BriefingPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  if (!DAY.test(date)) notFound();
  const [briefing, counts] = await Promise.all([reader.briefing(date), reader.taxonomy()]);
  if (!briefing) notFound();
  return <ThreePane nav={<TaxonomyTree counts={counts} />} main={<BriefingMain briefing={briefing} />} aside={<BriefingAside briefing={briefing} />} />;
}
