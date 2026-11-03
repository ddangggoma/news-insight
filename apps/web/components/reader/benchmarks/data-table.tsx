"use client";

import {
  type ColumnDef,
  type ExpandedState,
  type RowData,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Columns3 } from "lucide-react";
import { Fragment, type ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Plain-text name for the column menu (the header may be a node). */
    label?: string;
    /** Numbers line up on the right, as on the sites. */
    numeric?: boolean;
    /** Per-cell classes, e.g. the top-5 shading of a LiveBench column. */
    cellClassName?: (row: TData) => string | undefined;
  }
}

// Sticky first column: an opaque background so scrolled cells pass under it, and a hairline
// at its right edge. The hover colour is the row's own hover (muted at 50%) mixed opaque.
const STICKY = "sticky left-0 z-10 bg-card shadow-[inset_-1px_0_0_var(--border)]";
const STICKY_HOVER = "group-hover:bg-[color-mix(in_oklab,var(--muted)_50%,var(--card))]";

export interface DataTableProps<T> {
  // TanStack's accessor columns carry their value type; a mixed list needs `any` here.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<T, any>[];
  data: T[];
  /** Accessible name of the table. */
  label: string;
  getRowId: (row: T) => string;
  enableSorting?: boolean;
  enableColumnVisibility?: boolean;
  enableExpanding?: boolean;
  enableRowSelection?: boolean;
  /** Picks beyond this are disabled until one is cleared. */
  maxSelected?: number;
  /** Controlled selection (row ids, in pick order). */
  selected?: string[];
  onSelectedChange?: (ids: string[]) => void;
  /** What the checkbox does, read with the row's name: "비교에 추가". */
  selectLabel?: string;
  /** What the chevron opens: "세부 점수" → "세부 점수 펼치기". */
  expandLabel?: string;
  canExpand?: (row: T) => boolean;
  renderSubRow?: (row: T) => ReactNode;
  /** Name of a row for its checkbox and chevron labels. */
  rowName?: (row: T) => string;
  initialSorting?: SortingState;
  initialVisibility?: VisibilityState;
  /** Filters and toggles that sit left of the column menu. */
  toolbar?: ReactNode;
  emptyText?: string;
  className?: string;
}

/**
 * A TanStack Table over the shadcn table markup: sortable headers (aria-sort), a column menu,
 * expandable rows, capped multi-select. The first column stays put while the rest scrolls
 * sideways, and the selection box and expand chevron live in it so they never scroll away.
 */
export function DataTable<T>({
  columns,
  data,
  label,
  getRowId,
  enableSorting = true,
  enableColumnVisibility = false,
  enableExpanding = false,
  enableRowSelection = false,
  maxSelected,
  selected = [],
  onSelectedChange,
  selectLabel = "선택",
  expandLabel = "세부",
  canExpand,
  renderSubRow,
  rowName,
  initialSorting = [],
  initialVisibility = {},
  toolbar,
  emptyText = "표시할 모델이 없습니다",
  className,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [visibility, setVisibility] = useState<VisibilityState>(initialVisibility);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const full = maxSelected !== undefined && selected.length >= maxSelected;

  const table = useReactTable({
    data,
    columns,
    getRowId: (row) => getRowId(row),
    state: { sorting, columnVisibility: visibility, expanded, rowSelection: Object.fromEntries(selected.map((id) => [id, true])) },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setVisibility,
    onExpandedChange: setExpanded,
    enableSorting,
    enableExpanding,
    getRowCanExpand: (row) => enableExpanding && (canExpand ? canExpand(row.original) : true),
    enableRowSelection: (row) => enableRowSelection && (selected.includes(row.id) || !full),
    defaultColumn: { sortUndefined: "last" },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  });

  const toggle = (id: string) => onSelectedChange?.(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  const hideable = table.getAllLeafColumns().filter((column, index) => index > 0 && column.getCanHide());
  const visible = table.getVisibleLeafColumns().length;

  return (
    <div className={cn("space-y-2", className)}>
      {(toolbar || enableColumnVisibility) && (
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
          {enableColumnVisibility && hideable.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="ml-auto">
                  <Columns3 aria-hidden />열 선택
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel>보일 열</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {hideable.map((column) => (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    checked={column.getIsVisible()}
                    onCheckedChange={(value) => column.toggleVisibility(Boolean(value))}
                    onSelect={(event) => event.preventDefault()}
                  >
                    {column.columnDef.meta?.label ?? column.id}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      )}
      <div className="rounded-lg border">
        <Table aria-label={label} className="text-[13px]">
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id} className="hover:bg-transparent">
                {group.headers.map((header, index) => {
                  const meta = header.column.columnDef.meta;
                  const sorted = header.column.getIsSorted();
                  const content = header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext());
                  return (
                    <TableHead
                      key={header.id}
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                      className={cn("h-9 text-xs font-medium text-muted-foreground", meta?.numeric && "text-right", index === 0 && STICKY)}
                    >
                      {header.column.getCanSort() ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-sm hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                            sorted && "text-foreground",
                            meta?.numeric && "flex-row-reverse",
                          )}
                        >
                          {content}
                          {sorted === "asc" ? (
                            <ArrowUp className="size-3" aria-hidden />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="size-3" aria-hidden />
                          ) : (
                            <ArrowUpDown className="size-3 opacity-40" aria-hidden />
                          )}
                        </button>
                      ) : (
                        content
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={visible} className="h-20 text-center text-muted-foreground">
                  {emptyText}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => {
                const name = rowName ? rowName(row.original) : row.id;
                const isSelected = row.getIsSelected();
                return (
                  <Fragment key={row.id}>
                    <TableRow data-state={isSelected ? "selected" : undefined} className="group">
                      {row.getVisibleCells().map((cell, index) => {
                        const meta = cell.column.columnDef.meta;
                        const body = flexRender(cell.column.columnDef.cell, cell.getContext());
                        return (
                          <TableCell
                            key={cell.id}
                            className={cn(
                              "py-1.5",
                              meta?.numeric && "text-right tabular-nums",
                              meta?.cellClassName?.(row.original),
                              index === 0 && [STICKY, STICKY_HOVER, isSelected && "bg-muted"],
                            )}
                          >
                            {index === 0 && (enableRowSelection || enableExpanding) ? (
                              <div className="flex items-center gap-1.5">
                                {enableRowSelection && (
                                  <input
                                    type="checkbox"
                                    className="size-3.5 accent-primary"
                                    aria-label={`${name} ${selectLabel}`}
                                    checked={isSelected}
                                    disabled={!row.getCanSelect()}
                                    onChange={() => toggle(row.id)}
                                  />
                                )}
                                {enableExpanding &&
                                  (row.getCanExpand() ? (
                                    <button
                                      type="button"
                                      aria-expanded={row.getIsExpanded()}
                                      aria-label={`${expandLabel} ${row.getIsExpanded() ? "접기" : "펼치기"}`}
                                      title={name}
                                      onClick={row.getToggleExpandedHandler()}
                                      className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                                    >
                                      <ChevronRight className={cn("size-3.5 transition-transform", row.getIsExpanded() && "rotate-90")} aria-hidden />
                                    </button>
                                  ) : (
                                    <span className="w-[18px]" aria-hidden />
                                  ))}
                                <div className="min-w-0">{body}</div>
                              </div>
                            ) : (
                              body
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                    {row.getIsExpanded() && renderSubRow && (
                      <TableRow className="bg-muted/30 hover:bg-muted/30">
                        <TableCell colSpan={visible} className="p-0 whitespace-normal">
                          <div className="sticky left-0 max-w-[calc(100vw-4rem)] px-3 py-2.5 md:max-w-3xl">{renderSubRow(row.original)}</div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
