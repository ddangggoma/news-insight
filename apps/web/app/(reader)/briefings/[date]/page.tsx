import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BriefingAside } from "@/components/reader/briefing-aside";
import { BriefingMain } from "@/components/reader/briefing-main";
import { BriefingPanes } from "@/components/reader/briefing-panes";
import { briefings } from "@/lib/briefings";
import { formatBriefingDate } from "@/lib/format";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }): Promise<Metadata> {
  const { date } = await params;
  return { title: DAY.test(date) ? `${formatBriefingDate(date)} 브리핑` : "데일리 브리핑" };
}

export default async function BriefingPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  if (!DAY.test(date)) notFound();
  const [briefing, past] = await Promise.all([briefings.on(date), briefings.recent()]);
  if (!briefing) notFound();
  return <BriefingPanes main={<BriefingMain briefing={briefing} />} aside={<BriefingAside briefing={briefing} past={past} />} />;
}
