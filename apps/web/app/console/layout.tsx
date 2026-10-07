import type { ReactNode } from "react";

import { logout } from "@/app/login/actions";
import { AlertBanner } from "@/components/console/alert-banner";
import { AppSidebar } from "@/components/console/app-sidebar";
import { ThemeToggle } from "@/components/console/theme-toggle";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { api } from "@/lib/api";
import { requireAdmin, sessionToken } from "@/lib/session";
import type { AlertOut } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const admin = await requireAdmin();
  const [alerts, pendingUsers] = await Promise.all([
    api.get<AlertOut[]>("/api/admin/alerts", { limit: 20 }).catch(() => []),
    api
      .get<{ counts: { pending: number } }>("/api/admin/users", { status: "pending" }, { "X-Session-Token": await sessionToken() })
      .then((data) => data.counts.pending)
      .catch(() => 0),
  ]);
  return (
    <SidebarProvider>
      <AppSidebar pendingUsers={pendingUsers} />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <span className="text-sm text-muted-foreground">운영 콘솔</span>
          <div className="ml-auto flex items-center gap-1">
            <span className="hidden text-xs text-muted-foreground sm:inline">{admin.name}</span>
            <form action={logout}>
              <Button type="submit" variant="ghost" size="sm">
                로그아웃
              </Button>
            </form>
            <ThemeToggle />
          </div>
        </header>
        <AlertBanner alerts={alerts} />
        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
