"use client";

import { Play, RefreshCw } from "lucide-react";

import { collectNow, pauseSource, resumeSource } from "@/app/console/actions";
import { ActionButton } from "@/components/console/action-button";
import { PauseDialog } from "@/components/console/pause-dialog";
import type { SourceStatus } from "@/lib/types";

export function SourceActions({ sourceKey, status }: { sourceKey: string; status: SourceStatus }) {
  return (
    <>
      <ActionButton action={() => collectNow(sourceKey)} label="즉시 수집" pendingLabel="요청 중…" successMessage="수집 작업을 보냈습니다" icon={RefreshCw} />
      {status === "paused" ? (
        <ActionButton action={() => resumeSource(sourceKey)} label="재개" pendingLabel="재개 중…" successMessage="재개했습니다" variant="default" icon={Play} />
      ) : status !== "retired" ? (
        <PauseDialog action={(reason) => pauseSource(sourceKey, reason)} />
      ) : null}
    </>
  );
}
