import { OctagonAlert } from "lucide-react";
import Link from "next/link";

import type { AlertOut } from "@/lib/types";

/** Console-wide strip for open critical/warning alerts (links to the alerts page). */
export function AlertBanner({ alerts }: { alerts: AlertOut[] }) {
  const open = alerts.filter((alert) => !alert.resolved_at && alert.severity !== "info");
  if (!open.length) return null;
  const critical = open.some((alert) => alert.severity === "critical");
  return (
    <Link
      href="/console/alerts"
      role="alert"
      className={
        critical
          ? "flex items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive"
          : "flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-300"
      }
    >
      <OctagonAlert className="size-4 shrink-0" aria-hidden />
      <span className="truncate">
        운영 알림 {open.length}건 · {open[0].title}
      </span>
    </Link>
  );
}
