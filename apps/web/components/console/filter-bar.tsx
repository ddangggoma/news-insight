import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface FilterField {
  name: string;
  label: string;
  value?: string;
  options: { value: string; label: string }[];
}

function selectedLabel(field: FilterField): string {
  const option = field.options.find((candidate) => candidate.value === field.value);
  return option ? option.label : `전체 ${field.label}`;
}

export function FilterBar({
  fields,
  query,
  searchPlaceholder,
}: {
  fields: FilterField[];
  query?: string;
  searchPlaceholder?: string;
}) {
  return (
    <form method="get" className="flex flex-wrap items-center gap-2">
      {fields.map((field) => (
        <Select key={field.name} name={field.name} defaultValue={field.value ?? "all"}>
          <SelectTrigger className="w-40" aria-label={field.label}>
            {/* Explicit text so the server render already shows the current choice. */}
            <SelectValue placeholder={field.label}>{selectedLabel(field)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 {field.label}</SelectItem>
            {field.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}
      {searchPlaceholder ? (
        <div className="relative">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input name="q" defaultValue={query} placeholder={searchPlaceholder} className="w-64 pl-8" />
        </div>
      ) : null}
      <Button type="submit" variant="secondary">
        적용
      </Button>
    </form>
  );
}
