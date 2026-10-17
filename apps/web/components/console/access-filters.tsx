import { AppLink as Link } from "@/components/app-link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// a type, not an interface: it goes straight into withQuery's Record<string, QueryValue>
export type AccessFilterValues = {
  user?: string;
  ip?: string;
  since?: string;
  until?: string;
  kind?: string;
  path?: string;
  outcome?: string;
};

interface Choice {
  value: string;
  label: string;
}

function Picker({ name, label, value, options }: { name: string; label: string; value?: string; options: Choice[] }) {
  const selected = options.find((option) => option.value === value)?.label ?? `전체 ${label}`;
  return (
    <Select name={name} defaultValue={value ?? "all"}>
      <SelectTrigger className="w-44" aria-label={label}>
        <SelectValue placeholder={label}>{selected}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">전체 {label}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** One GET form for the three tabs; `kinds` and `outcomes` show only where they apply. */
export function AccessFilters({
  tab,
  values,
  accounts,
  kinds,
  outcomes,
}: {
  tab: string;
  values: AccessFilterValues;
  accounts: Choice[];
  kinds?: Choice[];
  outcomes?: Choice[];
}) {
  return (
    <form method="get" className="flex flex-wrap items-center gap-2" aria-label="접속 기록 필터">
      <input type="hidden" name="tab" value={tab} />
      <Picker name="user" label="계정" value={values.user} options={accounts} />
      {kinds ? <Picker name="kind" label="종류" value={values.kind} options={kinds} /> : null}
      {outcomes ? <Picker name="outcome" label="결과" value={values.outcome} options={outcomes} /> : null}
      {kinds ? (
        <Input name="path" defaultValue={values.path} placeholder="경로 (예: /radar)" aria-label="경로" className="w-48" maxLength={300} />
      ) : null}
      <Input name="ip" defaultValue={values.ip} placeholder="접속 주소" aria-label="접속 주소" className="w-40 font-mono" maxLength={45} />
      <Input type="date" name="since" defaultValue={values.since} aria-label="시작일" className="w-40" />
      <span className="text-sm text-muted-foreground">~</span>
      <Input type="date" name="until" defaultValue={values.until} aria-label="종료일" className="w-40" />
      <Button type="submit" variant="secondary">
        적용
      </Button>
      <Button asChild variant="ghost">
        <Link href={`/console/access?tab=${tab}`}>초기화</Link>
      </Button>
    </form>
  );
}
