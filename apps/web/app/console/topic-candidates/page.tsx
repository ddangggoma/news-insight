import Link from "next/link";

import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { FIELD_LABEL } from "@/lib/taxonomy";
import type { TopicCandidate } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "미분류 신호" };

const RANGES = [7, 30, 90] as const;

export default async function TopicCandidatesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const days = RANGES.find((d) => String(d) === param(sp, "days")) ?? 30;
  const candidates = await api.get<TopicCandidate[]>("/api/admin/topic-candidates", { days });
  return (
    <>
      <PageHeader
        title="미분류 신호"
        description="카드 분류기가 '테마 목록이 잘 맞지 않는다'고 남긴 기술·주제 후보입니다. 표기 차이(공백·하이픈)는 하나로 묶습니다. 자주 나오는 후보는 기술 레지스트리 항목이나 새 테마로 검토합니다(월 1회 체계 검토)."
        actions={
          <div className="flex gap-1">
            {RANGES.map((d) => (
              <Link
                key={d}
                href={`/console/topic-candidates?days=${d}`}
                aria-current={d === days ? "page" : undefined}
                className={cn("rounded-md border px-3 py-1 text-sm hover:bg-muted", d === days && "border-primary bg-primary/10 text-primary")}
              >
                {d}일
              </Link>
            ))}
          </div>
        }
      />
      {candidates.length === 0 ? (
        <EmptyState title="아직 후보가 없습니다" description="2건 이상 반복된 후보만 보입니다. 재분류가 진행되면 쌓입니다." />
      ) : (
        <ol className="divide-y rounded-lg border">
          {candidates.map((candidate, index) => (
            <li key={candidate.key} className="grid gap-2 p-4 md:grid-cols-[minmax(0,240px)_1fr]">
              <div className="space-y-1">
                <p className="font-medium">
                  <span className="mr-2 text-muted-foreground tabular-nums">{index + 1}</span>
                  {candidate.label}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatNumber(candidate.count)}건 · 최근 7일 {formatNumber(candidate.recent)}건
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDateTime(candidate.first_seen)} ~ {formatDateTime(candidate.last_seen)}
                </p>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(candidate.fields).map(([field, count]) => (
                    <Badge key={field} variant="outline" className="text-[11px]">
                      {FIELD_LABEL[field] ?? field} {count}
                    </Badge>
                  ))}
                </div>
              </div>
              <ul className="space-y-1 text-sm">
                {candidate.examples.map((item) => (
                  <li key={item.id} className="truncate">
                    <Link href={`/console/items/${item.id}`} className="hover:underline">
                      {item.title_ko ?? item.title}
                    </Link>
                    <span className="ml-2 text-xs text-muted-foreground">{item.source_name}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
