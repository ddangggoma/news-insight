"use client";

import { type ComponentProps, useTransition } from "react";

import { Button } from "@/components/ui/button";

/** An error boundary's "try again": re-fetches the segment and stays disabled until it answers,
 * so repeated clicks do not stack requests on a server that is already struggling. */
export function RetryButton({ retry, ...props }: { retry: () => void } & ComponentProps<typeof Button>) {
  const [pending, startTransition] = useTransition();
  return (
    <Button {...props} disabled={pending} aria-busy={pending} onClick={() => startTransition(() => retry())}>
      {pending ? "다시 불러오는 중…" : "다시 시도"}
    </Button>
  );
}
