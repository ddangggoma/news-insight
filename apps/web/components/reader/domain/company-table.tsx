"use client";

import { type ColumnDef, createColumnHelper } from "@tanstack/react-table";

import { AppLink as Link } from "@/components/app-link";
import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeBadge, WatchedBadge } from "@/components/reader/domain/parts";
import { type RankedCompany, orgTypeLabel } from "@/lib/domain-types";

export type RankRow = RankedCompany & { rank: number; href: string; selected: boolean };

const column = createColumnHelper<RankRow>();

// sorting a change puts "새로" (no previous window) above every ratio, and "–" last
const changeValue = (row: RankRow) => (row.previous === 0 ? (row.count > 0 ? Number.POSITIVE_INFINITY : undefined) : (row.change ?? 0));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const columns: ColumnDef<RankRow, any>[] = [
  column.accessor("label", {
    header: "이름",
    meta: { label: "이름" },
    sortingFn: "text",
    cell: (c) => {
      const row = c.row.original;
      const type = row.entity === "org" ? orgTypeLabel(row.org_type) : "";
      return (
        <div className="flex max-w-56 items-center gap-1.5 md:max-w-72">
          <span className="w-5 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{row.rank}</span>
          <Link href={row.href} aria-current={row.selected ? "true" : undefined} className="truncate font-medium hover:text-primary hover:underline aria-[current=true]:text-primary">
            {row.label}
          </Link>
          {row.watched ? <WatchedBadge relation={row.relation} /> : null}
          {type ? <span className="shrink-0 text-[11px] text-muted-foreground">{type}</span> : null}
        </div>
      );
    },
  }),
  column.accessor("count", { header: "문헌 수", meta: { label: "문헌 수", numeric: true }, sortDescFirst: true, cell: (c) => c.getValue() }),
  column.accessor("previous", { header: "직전", meta: { label: "직전", numeric: true }, sortDescFirst: true, cell: (c) => c.getValue() }),
  column.accessor(changeValue, {
    id: "change",
    header: "변화",
    meta: { label: "변화", numeric: true },
    sortDescFirst: true,
    cell: (c) => <ChangeBadge change={c.row.original.change} count={c.row.original.count} previous={c.row.original.previous} />,
  }),
  column.display({
    id: "fields",
    header: "주 분야",
    meta: { label: "주 분야" },
    cell: (c) => (
      <span className="text-xs text-ink-2">
        {c.row.original.top_fields.length ? c.row.original.top_fields.map((f) => `${f.label} ${f.count}`).join(" · ") : "–"}
      </span>
    ),
  }),
];

/** The 기업·기관 ranking: sortable columns, the name opens the detail below. */
export function CompanyTable({ rows, label, emptyText }: { rows: RankRow[]; label: string; emptyText: string }) {
  return <DataTable columns={columns} data={rows} label={label} getRowId={(row) => `${row.entity}:${row.key}`} emptyText={emptyText} initialLimit={15} />;
}
