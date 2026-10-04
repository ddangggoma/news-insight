import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { ClassificationBadges } from "@/components/console/classification";
import { EmptyState } from "@/components/console/empty-state";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { api } from "@/lib/api";
import { formatRelative, TRACK_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import { BUSINESS_LABEL } from "@/lib/taxonomy";
import type { Page, StoryView, Track } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "이슈 묶음" };

const RELATION_LABEL: Record<string, string> = { seed: "최초", exact: "동일 기사", near: "유사 보도", event: "같은 사건" };

export default async function StoriesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = {
    days: param(sp, "days") ?? "1",
    min_size: param(sp, "min_size") ?? "2",
    min_tracks: param(sp, "min_tracks"),
    track: param(sp, "track"),
    business: param(sp, "business"),
  };
  const focus = Number(param(sp, "focus") ?? 0);
  const page = pageParam(sp);
  const data = await api.get<Page<StoryView>>("/api/admin/stories", { ...filters, page });
  return (
    <>
      <PageHeader
        title="이슈 묶음"
        description="같은 기사(동일 URL·AMP·모바일), 유사 보도, 같은 사건을 한 이슈로 묶었습니다. 많은 매체가 다룬 이슈부터 보여 줍니다."
      />
      <FilterBar
        fields={[
          { name: "days", label: "기간", value: filters.days, options: [{ value: "1", label: "최근 1일" }, { value: "3", label: "최근 3일" }, { value: "7", label: "최근 7일" }] },
          { name: "min_size", label: "최소 기사 수", value: filters.min_size, options: [{ value: "1", label: "1건 이상" }, { value: "2", label: "2건 이상" }, { value: "3", label: "3건 이상" }, { value: "5", label: "5건 이상" }] },
          { name: "min_tracks", label: "트랙 수", value: filters.min_tracks, options: [{ value: "2", label: "2개 트랙 이상" }] },
          { name: "track", label: "트랙", value: filters.track, options: (Object.entries(TRACK_LABEL) as [Track, string][]).map(([value, label]) => ({ value, label })) },
          { name: "business", label: "사업부", value: filters.business, options: Object.entries(BUSINESS_LABEL).map(([value, label]) => ({ value, label })) },
        ]}
      />
      {data.items.length === 0 ? (
        <EmptyState title="조건에 맞는 이슈가 없습니다" description="카드가 만들어진 항목은 5분마다 이슈로 묶입니다." />
      ) : (
        <div className="space-y-4">
          {data.items.map((story) => (
            <article
              key={story.id}
              id={`story-${story.id}`}
              className={cn("rounded-xl border bg-card p-4", focus === story.id && "border-primary ring-2 ring-primary/20")}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {story.tracks.map((track) => (
                  <TrackBadge key={track} track={track} />
                ))}
                <span>기사 {story.item_count}건 · 매체 {story.source_count}곳</span>
                <span className="ml-auto">{formatRelative(story.last_seen_at)}</span>
              </div>
              <h3 className="mt-2 text-lg leading-snug font-semibold text-balance">
                <Link href={`/console/items/${story.representative.id}`} className="hover:underline">
                  {story.title_ko ?? story.representative.title}
                </Link>
              </h3>
              {story.card ? (
                <div className="mt-2">
                  <ClassificationBadges card={story.card} />
                </div>
              ) : null}
              {story.card && story.card.summary_ko.length > 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">{story.card.summary_ko.join(" ")}</p>
              ) : null}
              <ul className="mt-3 divide-y border-t text-sm">
                {story.members.map((member) => (
                  <li key={member.item.id} className="flex items-center gap-2 py-2">
                    <span className="w-16 shrink-0 text-xs text-muted-foreground">{RELATION_LABEL[member.relation]}</span>
                    <Link href={`/console/items/${member.item.id}`} className="min-w-0 flex-1 truncate hover:underline">
                      {member.item.title_ko ?? member.item.title}
                    </Link>
                    <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">{member.item.source_name}</span>
                    <a href={member.item.url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="원문">
                      <ExternalLink className="size-3.5" />
                    </a>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
      <PaginationBar pathname="/console/stories" params={filters} page={page} size={data.size} total={data.total} />
    </>
  );
}
