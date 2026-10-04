import Link from "next/link";

import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { CandidateActions, TechnologyEditor } from "@/components/console/technology-forms";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import type { TechnologyCandidate, TechnologyOut } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "기술 레지스트리" };

const KIND_LABEL = { technology: "기술", standard: "표준", regulation: "규제", product_family: "제품군" } as const;
const STATUS_LABEL = { active: "활성", watch: "감시", ignored: "무시" } as const;

export default async function TechnologiesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const q = param(sp, "q");
  const status = param(sp, "status");
  const [techs, all, candidates] = await Promise.all([
    api.get<TechnologyOut[]>("/api/admin/technologies", { q, status }),
    api.get<TechnologyOut[]>("/api/admin/technologies"),
    api.get<TechnologyCandidate[]>("/api/admin/technologies/candidates", { days: 30, min_count: 10 }),
  ]);
  const themes = [...new Set(all.map((t) => t.theme_key).filter((t): t is string => Boolean(t)))].sort();
  const keys = all.filter((t) => t.status !== "ignored").map((t) => t.key);
  return (
    <>
      <PageHeader
        title="기술 레지스트리"
        description="분류의 3단계 '기술'입니다. 카드 키워드는 저장될 때 여기의 키와 별칭으로 정규화되고(technology_keys), 레이더의 기술 축이 이 키를 씁니다. 편집하면 해당 카드 키를 바로 다시 계산합니다."
      />
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">
          후보 대기열 <span className="font-normal text-muted-foreground">최근 30일 DX 관련 카드 10건 이상, 레지스트리에 없는 키워드</span>
        </h2>
        {candidates.length === 0 ? (
          <EmptyState title="처리할 후보가 없습니다" />
        ) : (
          <ul className="divide-y rounded-lg border">
            {candidates.map((candidate) => (
              <li key={candidate.key} className="flex flex-wrap items-center gap-3 p-3">
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{candidate.label}</span>
                  <span className="ml-2 font-mono text-xs text-muted-foreground">{candidate.key}</span>
                </span>
                <span className="text-sm text-muted-foreground tabular-nums">{formatNumber(candidate.count)}건</span>
                <CandidateActions candidate={candidate} themes={themes} keys={keys} />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold">등록된 기술 {formatNumber(techs.length)}개</h2>
          <form className="ml-auto flex gap-2" action="/console/technologies">
            <Input name="q" defaultValue={q} placeholder="이름·키·별칭 검색" className="h-8 w-48" />
            {status ? <input type="hidden" name="status" value={status} /> : null}
          </form>
          <div className="flex gap-1">
            {[undefined, "active", "watch", "ignored"].map((s) => (
              <Link
                key={s ?? "all"}
                href={`/console/technologies${s ? `?status=${s}` : ""}`}
                className={cn("rounded-md border px-2 py-1 text-xs hover:bg-muted", status === s && "border-primary bg-primary/10 text-primary")}
              >
                {s ? STATUS_LABEL[s as keyof typeof STATUS_LABEL] : "전체"}
              </Link>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2">기술</th>
                <th className="p-2">테마</th>
                <th className="p-2">종류·상태</th>
                <th className="p-2">별칭</th>
                <th className="p-2 text-right">30일</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {techs.map((tech) => (
                <tr key={tech.key} className="align-top">
                  <td className="p-2">
                    <span className="font-medium">{tech.label}</span>
                    <span className="block font-mono text-xs text-muted-foreground">{tech.key}</span>
                  </td>
                  <td className="p-2 font-mono text-xs">{tech.theme_key ?? "—"}</td>
                  <td className="p-2">
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="outline">{KIND_LABEL[tech.kind]}</Badge>
                      <Badge variant={tech.status === "watch" ? "secondary" : "outline"}>{STATUS_LABEL[tech.status]}</Badge>
                    </div>
                  </td>
                  <td className="max-w-xs p-2 text-xs text-muted-foreground">{tech.aliases.join(", ") || "—"}</td>
                  <td className="p-2 text-right tabular-nums">{formatNumber(tech.cards_30d)}</td>
                  <td className="p-2">
                    <TechnologyEditor tech={tech} themes={themes} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
