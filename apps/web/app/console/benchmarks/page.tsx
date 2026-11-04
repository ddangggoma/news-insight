import { LinkModelForm } from "@/components/console/benchmark-forms";
import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { UnmatchedModel } from "@/lib/types";

export const metadata = { title: "모델 이름 연결" };

export default async function BenchmarksPage() {
  const unmatched = await api.get<UnmatchedModel[]>("/api/admin/benchmarks/unmatched");
  return (
    <>
      <PageHeader
        title="모델 이름 연결"
        description="벤치마크 사이트가 쓰는 모델 이름 가운데 아직 어떤 모델에도 연결되지 않은 것입니다. 이름을 고쳐 연결하면 모델이 없을 때 새로 만들고, 같은 표기(괄호 설정·대소문자·구분 기호만 다른 경우 포함)의 점수 전체에 채웁니다. 연결한 표기는 다음 수집부터 자동으로 맞춰집니다."
      />
      {unmatched.length === 0 ? (
        <EmptyState title="연결할 이름이 없습니다" description="사이트별 최신 수집분의 모든 모델이 연결되어 있습니다." />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2">사이트 표기</th>
                <th className="p-2">사이트</th>
                <th className="p-2">최근 수집</th>
                <th className="p-2">모델 이름 · 제작사</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {unmatched.map((model) => (
                <tr key={model.model_raw} className="align-top">
                  <td className="p-2 font-medium">{model.model_raw}</td>
                  <td className="p-2 text-xs text-muted-foreground">{model.sites.join(", ")}</td>
                  <td className="p-2 text-xs text-muted-foreground">{formatDateTime(model.last_seen)}</td>
                  <td className="p-2">
                    <LinkModelForm model={model} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
