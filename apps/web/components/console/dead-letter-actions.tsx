"use client";

import { RotateCcw, X } from "lucide-react";

import { dismissDeadLetter, retryDeadLetter } from "@/app/console/actions";
import { ActionButton } from "@/components/console/action-button";

export function DeadLetterActions({ id }: { id: number }) {
  return (
    <div className="flex justify-end gap-2">
      <ActionButton action={() => retryDeadLetter(id)} label="재시도" pendingLabel="처리 중…" successMessage="즉시 재수집하도록 예약했습니다" icon={RotateCcw} />
      <ActionButton action={() => dismissDeadLetter(id)} label="종결" pendingLabel="처리 중…" successMessage="종결했습니다" variant="ghost" icon={X} />
    </div>
  );
}
