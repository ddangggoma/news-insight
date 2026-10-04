import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

import { FieldPicker } from "@/components/reader/radar/field-picker";
import { RADAR_KINDS, radarHref, type RadarView } from "@/lib/radar";
import { withQuery } from "@/lib/query";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import type { Radar, RadarKind } from "@/lib/reader-types";
import { FIELD_LABEL, SIGNAL_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const segment = "rounded-md px-3 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground";
const segmentOn = "bg-background font-semibold text-foreground shadow-sm";

export function RadarControls({ radar, view }: { radar: Radar; view: RadarView }) {
  const { window } = radar;
  const keep = { scope: view.scope, signal: view.signal, field: view.field };
  const at = (patch: Partial<RadarView>) => radarHref(window.kind, window.key, { ...keep, ...patch });
  const fieldHrefs = Object.fromEntries([["*", at({ field: null })], ...Object.keys(FIELD_LABEL).map((field) => [field, at({ field })])]);
  const toggle = (signal: string) =>
    view.signal.includes(signal) ? view.signal.filter((s) => s !== signal) : [...view.signal, signal];

  return (
    <div className="space-y-3 rounded-2xl border bg-card/70 p-3 shadow-xs backdrop-blur md:p-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <nav aria-label="기간 단위" className="inline-flex rounded-lg bg-muted p-0.5">
          {(Object.keys(RADAR_KINDS) as RadarKind[]).map((kind) => (
            <Link
              key={kind}
              href={withQuery("/radar", { period: kind, scope: view.scope !== "relevant" ? view.scope : undefined, signal: view.signal, field: view.field ?? undefined })}
              aria-current={window.kind === kind ? "true" : undefined}
              className={cn(segment, window.kind === kind && segmentOn)}
            >
              {RADAR_KINDS[kind]}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-1">
          <Link href={radarHref(window.kind, window.prev_key, keep)} aria-label="이전 기간" className="grid size-8 place-items-center rounded-lg hover:bg-muted">
            <ChevronLeft className="size-4" aria-hidden />
          </Link>
          <span className="min-w-20 text-center text-base font-bold tabular-nums">{window.key}</span>
          {window.is_current ? (
            <span className="grid size-8 place-items-center text-muted-foreground/40" aria-hidden>
              <ChevronRight className="size-4" />
            </span>
          ) : (
            <Link href={radarHref(window.kind, window.next_key, keep)} aria-label="다음 기간" className="grid size-8 place-items-center rounded-lg hover:bg-muted">
              <ChevronRight className="size-4" aria-hidden />
            </Link>
          )}
        </div>
        {window.elapsed !== null ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground" title="진행 중인 기간은 끝난 직전 기간과 그대로 비교합니다">
            <span className="rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">진행 중</span>
            <span className="relative h-1.5 w-20 overflow-hidden rounded-full bg-muted" aria-hidden>
              <span className="absolute inset-y-0 left-0 rounded-full bg-primary/60" style={{ width: `${Math.round(window.elapsed * 100)}%` }} />
            </span>
            <span className="tabular-nums">{Math.round(window.elapsed * 100)}% 경과</span>
          </div>
        ) : null}
        <nav aria-label="범위" className="inline-flex rounded-lg bg-muted p-0.5 lg:ml-auto">
          {(Object.keys(SCOPES) as Scope[]).map((scope) => (
            <Link key={scope} href={at({ scope })} aria-current={view.scope === scope ? "true" : undefined} className={cn(segment, "px-2.5", view.scope === scope && segmentOn)}>
              {SCOPES[scope]}
            </Link>
          ))}
        </nav>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3">
        <FieldPicker value={view.field} hrefs={fieldHrefs} />
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="신호 유형 필터">
          <span className="mr-1 text-sm text-muted-foreground">신호 유형</span>
          <Link
            href={at({ signal: [] })}
            aria-current={view.signal.length === 0 ? "true" : undefined}
            className={cn("rounded-full border px-2.5 py-0.5 text-xs", view.signal.length === 0 ? "border-foreground bg-foreground text-background" : "hover:bg-muted")}
          >
            전체
          </Link>
          {Object.keys(SIGNAL_LABEL).map((signal) => {
            const on = view.signal.includes(signal);
            return (
              <Link
                key={signal}
                href={at({ signal: toggle(signal) })}
                aria-pressed={on}
                title={SIGNAL_LABEL[signal]}
                className={cn("rounded-full border px-2.5 py-0.5 text-xs", on ? "border-primary bg-primary/10 font-semibold text-primary" : "hover:bg-muted")}
              >
                {SIGNAL_LABEL[signal]}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
