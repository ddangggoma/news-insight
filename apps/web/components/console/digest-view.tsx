import { Lightbulb } from "lucide-react";

import { DigestStatusBadge, TrackBadge } from "@/components/console/badges";
import { EvidenceLinks } from "@/components/console/evidence-links";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CATEGORY_LABEL, formatDateTime, formatNumber } from "@/lib/format";
import type { DigestOut } from "@/lib/types";

export function DigestView({ digest }: { digest: DigestOut }) {
  const { content } = digest;
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <DigestStatusBadge status={digest.status} />
          <span>{digest.digest_date} 발행</span>
          <span>· 수집 {formatNumber(digest.item_count)}건</span>
          <span>· 생성 {formatDateTime(digest.generated_at)}</span>
          {digest.model ? <span>· {digest.model}</span> : null}
        </div>
        <h2 className="text-3xl font-semibold tracking-tight text-balance">{content.headline}</h2>
        <p className="max-w-3xl leading-relaxed text-muted-foreground">{content.overview}</p>
      </section>

      {content.insights.length > 0 ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Lightbulb className="size-5 text-primary" aria-hidden /> 종합 인사이트
          </h3>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {content.insights.map((insight) => (
              <article key={insight.title} className="min-w-0">
                <Card className="h-full">
                  <CardHeader>
                    <CardTitle className="text-base">{insight.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm leading-relaxed">
                    <p>{insight.body}</p>
                    <EvidenceLinks ids={insight.item_ids} items={digest.items} />
                  </CardContent>
                </Card>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        {content.tracks.map((track) => (
          <Card key={track.track}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <TrackBadge track={track.track} />
              </div>
              <CardDescription className="leading-relaxed">{track.summary}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-x-8 gap-y-6 md:grid-cols-2 [&>*]:min-w-0">
              {track.categories.map((category) => (
                <div key={category.category} className="space-y-2">
                  <p className="text-sm font-medium">
                    {CATEGORY_LABEL[category.category] ?? category.category}
                    <span className="ml-2 font-normal text-muted-foreground">{category.headline}</span>
                  </p>
                  <ul className="space-y-2 text-sm">
                    {category.points.map((point) => (
                      <li key={point.text} className="flex flex-col gap-1 border-l-2 pl-3">
                        <span>{point.text}</span>
                        <EvidenceLinks ids={point.item_ids} items={digest.items} />
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
