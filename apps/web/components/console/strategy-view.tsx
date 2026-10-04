import { Compass, ShieldCheck, Users } from "lucide-react";

import { shortBusiness } from "@/components/console/classification";
import { EvidenceLinks } from "@/components/console/evidence-links";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StrategyClaim, StrategyOut } from "@/lib/types";
import { cn } from "@/lib/utils";

const GROUP_LABEL = { executive: "경영진", business: "사업부장", domain: "기술·도메인 리더" } as const;
const HORIZON_LABEL = { "1y": "1년", "3y": "3년", "5y": "5년" } as const;

function Claims({ claims, items }: { claims: StrategyClaim[]; items: StrategyOut["items"] }) {
  return (
    <ul className="space-y-2 text-sm">
      {claims.map((claim) => (
        <li key={claim.id} className="flex flex-col gap-1 border-l-2 pl-3">
          <span>{claim.text}</span>
          <EvidenceLinks ids={claim.item_ids} items={items} />
        </li>
      ))}
    </ul>
  );
}

export function StrategyView({ strategy }: { strategy: StrategyOut }) {
  const report = strategy.report;
  const insights = strategy.personas.filter((p) => p.status === "insight");
  return (
    <div className="space-y-6">
      {report ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Compass className="size-5 text-primary" /> 데일리 전략 보고서
            </CardTitle>
            {strategy.review ? (
              <Badge variant={strategy.review.verdict === "pass" ? "default" : "outline"}>
                <ShieldCheck /> 리뷰 {strategy.review.verdict === "pass" ? "통과" : `수정 ${strategy.dropped_claims}건 반영`}
              </Badge>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-6">
            <p className="leading-relaxed">{report.summary}</p>
            {report.businesses.length > 0 ? (
              <div className="grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
                {report.businesses.map((section) => (
                  <div key={section.business} className="space-y-2">
                    <p className="text-sm font-semibold">
                      <span className="mr-2 rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary">{shortBusiness(section.business)}</span>
                      {section.summary}
                    </p>
                    <Claims claims={section.claims} items={strategy.items} />
                  </div>
                ))}
              </div>
            ) : null}
            {report.roadmap.length > 0 ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold">로드맵 시사점</p>
                <div className="grid gap-4 md:grid-cols-3 [&>*]:min-w-0">
                  {(["1y", "3y", "5y"] as const).map((horizon) => (
                    <div key={horizon} className="space-y-2 rounded-lg border p-3">
                      <p className="text-xs font-medium text-muted-foreground">{HORIZON_LABEL[horizon]}</p>
                      <Claims claims={report.roadmap.filter((r) => r.horizon === horizon)} items={strategy.items} />
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="grid gap-6 md:grid-cols-2 [&>*]:min-w-0">
              <div className="space-y-2">
                <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">기회</p>
                <Claims claims={report.opportunities} items={strategy.items} />
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold text-rose-700 dark:text-rose-300">위험</p>
                <Claims claims={report.risks} items={strategy.items} />
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">전략 보고서를 만들지 못했습니다{strategy.error ? `: ${strategy.error}` : ""}</CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="size-5 text-primary" /> 페르소나 인사이트
            <span className="text-sm font-normal text-muted-foreground">
              {insights.length}/30 신호 · 나머지 no_signal
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {(["executive", "business", "domain"] as const).map((group) => (
            <div key={group} className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">{GROUP_LABEL[group]}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 [&>*]:min-w-0">
                {strategy.personas
                  .filter((p) => p.group === group)
                  .map((persona) => (
                    <div
                      key={persona.key}
                      className={cn("space-y-1.5 rounded-lg border p-3 text-sm", persona.status === "no_signal" && "border-dashed opacity-60")}
                    >
                      <p className="flex items-center gap-2 font-medium">
                        {persona.name}
                        {persona.status === "no_signal" ? <span className="text-xs font-normal text-muted-foreground">no_signal</span> : null}
                      </p>
                      {persona.status === "insight" ? (
                        <>
                          <p className="font-semibold">{persona.headline}</p>
                          <p className="text-muted-foreground">{persona.insight}</p>
                          {persona.actions.length > 0 ? (
                            <ul className="list-disc pl-4 text-xs text-muted-foreground">
                              {persona.actions.map((action) => (
                                <li key={action}>{action}</li>
                              ))}
                            </ul>
                          ) : null}
                          <EvidenceLinks ids={persona.item_ids} items={strategy.items} />
                        </>
                      ) : null}
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
