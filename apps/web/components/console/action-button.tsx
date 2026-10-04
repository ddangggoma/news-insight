"use client";

import type { LucideIcon } from "lucide-react";
import { useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

export function ActionButton({
  action,
  label,
  pendingLabel,
  successMessage,
  variant = "outline",
  icon: Icon,
}: {
  action: () => Promise<void>;
  label: string;
  pendingLabel: string;
  successMessage: string;
  variant?: "default" | "outline" | "secondary" | "destructive" | "ghost";
  icon?: LucideIcon;
}) {
  const [pending, startTransition] = useTransition();
  return (
    <Button
      variant={variant}
      size="sm"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          try {
            await action();
            toast.success(successMessage);
          } catch (error) {
            toast.error(error instanceof Error ? error.message : "요청에 실패했습니다");
          }
        })
      }
    >
      {Icon ? <Icon /> : null}
      {pending ? pendingLabel : label}
    </Button>
  );
}
