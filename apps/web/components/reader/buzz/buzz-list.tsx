import { Zap } from "lucide-react";

import { AppLink as Link } from "@/components/app-link";
import { Badge } from "@/components/ui/badge";
import { type BuzzCluster, headline, leadLabel, platformLabel } from "@/lib/buzz-types";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 속보 or 화제, and for breaking ones how far ahead of the news the community was. */
function Status({ cluster }: { cluster: BuzzCluster }) {
  const lead = leadLabel(cluster);
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {cluster.breaking ? (
        <Badge variant="destructive">
          <Zap aria-hidden />
          속보
        </Badge>
      ) : (
        <Badge variant="secondary">화제</Badge>
      )}
      {lead && <span className="text-xs font-medium text-impact-risk">{lead}</span>}
    </span>
  );
}

/** One cluster: status, Korean title and summary (the lead post's words until it is written), who is talking, posts and the news. */
export function BuzzCard({ cluster, now }: { cluster: BuzzCluster; now?: Date }) {
  return (
    <article id={`c${cluster.id}`} aria-labelledby={`c${cluster.id}-title`} className="scroll-mt-24 space-y-2 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Status cluster={cluster} />
        <span className="text-xs text-muted-foreground tabular-nums">
          {`첫 글 ${formatRelative(cluster.first_seen_at, now)} · 최근 ${formatRelative(cluster.last_seen_at, now)}`}
        </span>
      </div>
      <h2 id={`c${cluster.id}-title`} className="font-semibold leading-snug">
        {cluster.title}
        {!cluster.summarized && <span className="ml-2 text-xs font-normal text-muted-foreground">(요약 작성 전, 원문)</span>}
      </h2>
      {cluster.summary.length > 0 && (
        <div className="space-y-0.5 text-sm text-muted-foreground">
          {cluster.summary.map((line, index) => (
            // engines can repeat a line: the position keeps the keys unique
            <p key={`${index}:${line}`}>{line}</p>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {`${cluster.platforms.map(platformLabel).join(" · ")} — ${cluster.authors}명 · 글 ${cluster.posts}건 · 반응 ${cluster.heat.toFixed(1)}`}
      </p>
      {cluster.keywords.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label="키워드">
          {cluster.keywords.map((word) => (
            <li key={word} className="rounded-sm bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground">
              {word}
            </li>
          ))}
        </ul>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground">{`커뮤니티 글 ${cluster.sample.length}건 보기`}</summary>
        <ul className="mt-1 space-y-1">
          {cluster.sample.map((post) => (
            <li key={post.id} className="flex gap-2">
              <span className="w-24 shrink-0 text-xs text-muted-foreground">{platformLabel(post.platform)}</span>
              <a href={post.url} target="_blank" rel="noopener noreferrer" className="min-w-0 break-words hover:text-primary hover:underline">
                {post.title}
              </a>
            </li>
          ))}
        </ul>
      </details>
      {cluster.news.length > 0 && (
        <div className="text-sm">
          <span className="text-xs text-muted-foreground">관련 뉴스</span>
          <ul className="space-y-0.5">
            {cluster.news.map((item) => (
              <li key={item.id}>
                <Link href={`/items/${item.id}`} className="hover:text-primary hover:underline">
                  {item.title}
                </Link>
                <span className="ml-1 text-xs text-muted-foreground">{item.source_name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

export function BuzzList({ clusters, now }: { clusters: BuzzCluster[]; now?: Date }) {
  if (clusters.length === 0)
    return (
      <div className="py-16 text-center">
        <p className="font-semibold">지금 화제인 커뮤니티 이야기가 없습니다</p>
        <p className="mt-1 text-sm text-muted-foreground">여러 커뮤니티에서 동시에 이야기되기 시작하면 여기에 나타납니다.</p>
      </div>
    );
  return (
    <div className="divide-y">
      {clusters.map((cluster) => (
        <BuzzCard key={cluster.id} cluster={cluster} now={now} />
      ))}
    </div>
  );
}

/** The explore page's band: up to three, breaking first, linking into the 화제·속보 page. Never part of the feed. */
export function BuzzStrip({ clusters }: { clusters: BuzzCluster[] }) {
  const shown = headline(clusters, 3);
  if (shown.length === 0) return null;
  return (
    <section aria-label="커뮤니티 화제·속보" className="rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold text-muted-foreground">커뮤니티 화제·속보</h2>
        <Link href="/buzz" className="text-xs text-muted-foreground hover:text-primary">
          전체 보기 →
        </Link>
      </div>
      <ul className="mt-1 space-y-1">
        {shown.map((cluster) => (
          <li key={cluster.id} className="flex min-w-0 items-center gap-2 text-sm">
            <span className={cn("shrink-0 text-xs font-semibold", cluster.breaking ? "text-impact-risk" : "text-muted-foreground")}>
              {cluster.breaking ? "속보" : "화제"}
            </span>
            <Link href={`/buzz#c${cluster.id}`} className="min-w-0 truncate hover:text-primary hover:underline">
              {cluster.title}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
