import { Download } from "lucide-react";

const FORMATS = [
  { format: "md", label: "Markdown" },
  { format: "docx", label: "Word" },
  { format: "pptx", label: "PowerPoint" },
] as const;

/** Download links for a report (plan 16 #11); `path` is under /export, e.g. "briefing/2026-10-09". */
export function ExportLinks({ path }: { path: string }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground" aria-label="내보내기">
      <Download className="size-3.5" aria-hidden />
      내보내기
      {FORMATS.map((f) => (
        <a key={f.format} href={`/export/${path}?format=${f.format}`} download className="rounded border px-1.5 py-0.5 hover:bg-muted hover:text-foreground">
          {f.label}
        </a>
      ))}
    </p>
  );
}
