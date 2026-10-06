import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PeriodicView, periodTitle } from "@/components/reader/periodic-view";
import { periodic } from "@/lib/briefings";

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }): Promise<Metadata> {
  const { key } = await params;
  return { title: periodTitle("month", key) };
}

export default async function MonthlyBriefingPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const period = await periodic.on("month", key);
  if (!period) notFound();
  return <PeriodicView period={period} />;
}
