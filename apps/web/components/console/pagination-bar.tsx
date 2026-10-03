import Link from "next/link";

import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { pageHref, type QueryValue } from "@/lib/query";

export function PaginationBar({
  pathname,
  params,
  page,
  size,
  total,
}: {
  pathname: string;
  params: Record<string, QueryValue>;
  page: number;
  size: number;
  total: number;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
      <span>
        총 {formatNumber(total)}건 · {page}/{pages} 페이지
      </span>
      <div className="flex gap-2">
        {page > 1 ? (
          <Button asChild variant="outline" size="sm">
            <Link href={pageHref(pathname, params, page - 1)}>이전</Link>
          </Button>
        ) : (
          <Button variant="outline" size="sm" disabled>
            이전
          </Button>
        )}
        {page < pages ? (
          <Button asChild variant="outline" size="sm">
            <Link href={pageHref(pathname, params, page + 1)}>다음</Link>
          </Button>
        ) : (
          <Button variant="outline" size="sm" disabled>
            다음
          </Button>
        )}
      </div>
    </div>
  );
}
