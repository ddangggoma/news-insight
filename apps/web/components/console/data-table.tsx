import type { Key, ReactNode } from "react";

import { EmptyState } from "@/components/console/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface Column<T> {
  key: string;
  header: string;
  className?: string;
  cell: (row: T) => ReactNode;
}

/** Column headers keep width and alignment from the cell classes, never their colors or fonts. */
function headClass(className?: string): string | undefined {
  return className
    ?.split(/\s+/)
    .filter((token) => /^(w-|min-w-|max-w-|text-(left|right|center)$)/.test(token))
    .join(" ");
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyTitle,
  emptyDescription,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => Key;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  if (rows.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return (
    <div className="overflow-hidden rounded-lg border">
      <Table>
        <TableHeader className="bg-muted/50">
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.key} className={headClass(column.className)}>
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((column) => (
                <TableCell key={column.key} className={column.className}>
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
