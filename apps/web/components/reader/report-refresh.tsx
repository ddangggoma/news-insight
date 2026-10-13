"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Reloads the server page while a report is waiting or being written. */
export function ReportRefresh({ seconds = 15 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = window.setInterval(() => router.refresh(), seconds * 1000);
    return () => window.clearInterval(timer);
  }, [router, seconds]);
  return null;
}
