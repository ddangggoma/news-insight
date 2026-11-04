"use client";

import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The app's detail view (2026-10-27): a centred dialog with a fixed header and its own scroll,
 * replacing the right-hand slide-over. Full screen on phones. Radix keeps focus inside, Esc closes,
 * and focus returns to the link that opened it.
 */
export function DetailDialog({
  open,
  onOpenChange,
  title,
  label,
  description,
  actions,
  size = "lg",
  children,
  bodyClassName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Accessible name; shown in the header unless `label` is given (the body then carries its own heading). */
  title: string;
  /** Short context shown in the header in place of the title, e.g. "기사". */
  label?: ReactNode;
  description?: string;
  actions?: ReactNode;
  size?: "md" | "lg" | "xl" | "full";
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 duration-200 ease-out data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0 data-closed:duration-150 dark:bg-black/60" />
        <DialogPrimitive.Content
          className={cn(
            "fixed inset-0 z-50 flex flex-col bg-background text-foreground outline-none",
            "sm:inset-auto sm:top-1/2 sm:left-1/2 sm:max-h-[calc(100dvh-3rem)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:shadow-2xl sm:ring-1 sm:ring-foreground/10",
            size === "md" && "sm:w-[min(40rem,calc(100vw-3rem))]",
            size === "lg" && "sm:w-[min(56rem,calc(100vw-3rem))]",
            size === "xl" && "sm:w-[min(72rem,calc(100vw-3rem))]",
            size === "full" && "sm:h-[calc(100dvh-3rem)] sm:w-[calc(100vw-3rem)]",
            "duration-200 ease-[cubic-bezier(0.16,1,0.3,1)] data-open:animate-in data-open:fade-in-0 data-open:zoom-in-[0.97] data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-[0.98] data-closed:duration-150 data-closed:ease-in max-sm:data-open:zoom-in-100 max-sm:data-open:slide-in-from-bottom-6",
          )}
        >
          <header className="flex min-h-14 shrink-0 items-center gap-2 border-b bg-card/80 py-2 pr-2 pl-5 sm:rounded-t-2xl">
            {label ? (
              <>
                {/* the body carries the visible heading; the title only names the dialog */}
                <DialogPrimitive.Title asChild>
                  <span className="sr-only">{title}</span>
                </DialogPrimitive.Title>
                <div className="min-w-0 flex-1 truncate text-sm font-semibold text-ink-2">{label}</div>
              </>
            ) : (
              <DialogPrimitive.Title className="min-w-0 flex-1 truncate text-base font-bold tracking-tight">{title}</DialogPrimitive.Title>
            )}
            <DialogPrimitive.Description className="sr-only">{description ?? title}</DialogPrimitive.Description>
            {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
            <DialogPrimitive.Close className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
              <XIcon className="size-5" aria-hidden />
              <span className="sr-only">닫기 (Esc)</span>
            </DialogPrimitive.Close>
          </header>
          <div className={cn("min-h-0 flex-1 overflow-y-auto overscroll-contain", bodyClassName)}>{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/** Header action: an icon with a visible short label from `sm` up. */
export function DialogAction({ href, external, icon, children }: { href: string; external?: boolean; icon: ReactNode; children: ReactNode }) {
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noreferrer" : undefined}
      className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-2 transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {icon}
      <span className="max-sm:sr-only">{children}</span>
    </a>
  );
}
