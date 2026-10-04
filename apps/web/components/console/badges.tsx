import { Badge } from "@/components/ui/badge";
import { OUTCOME_LABEL, STATUS_LABEL, TRACK_LABEL } from "@/lib/format";
import type { DigestStatus, Outcome, SourceStatus, Stage, Track } from "@/lib/types";

type Variant = "default" | "secondary" | "destructive" | "outline";

const STATUS_VARIANT: Record<SourceStatus, Variant> = {
  active: "default",
  candidate: "secondary",
  paused: "destructive",
  retired: "outline",
};

const OUTCOME_VARIANT: Record<Outcome, Variant> = {
  success: "default",
  not_modified: "secondary",
  failed: "outline",
  dead_lettered: "destructive",
  skipped: "outline",
};

export function StatusBadge({ status }: { status: SourceStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function StageBadge({ stage }: { stage: Stage }) {
  return (
    <Badge variant="outline" className="font-mono">
      {stage === "unverified" ? "미검증" : stage}
    </Badge>
  );
}

export function TrackBadge({ track }: { track: Track }) {
  return <Badge variant="secondary">{TRACK_LABEL[track]}</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return <Badge variant={OUTCOME_VARIANT[outcome]}>{OUTCOME_LABEL[outcome]}</Badge>;
}

export function DigestStatusBadge({ status }: { status: DigestStatus }) {
  return status === "published" ? (
    <Badge>Claude 요약</Badge>
  ) : (
    <Badge variant="outline">규칙 기반 대체본</Badge>
  );
}
