"use client";

import { Download, ExternalLink, Trash2, Upload } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/console/empty-state";
import { Button } from "@/components/ui/button";
import { useLibrary } from "@/hooks/use-library";
import { formatDateTime } from "@/lib/format";
import { exportLibrary, mergeLibraries, parseLibrary } from "@/lib/library";

export function LibraryView() {
  const { library, update, toggleBookmark } = useLibrary();
  const input = useRef<HTMLInputElement>(null);
  const saved = Object.values(library.bookmarks).sort((a, b) => b.saved_at.localeCompare(a.saved_at));

  const download = () => {
    const blob = new Blob([exportLibrary(library, new Date())], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `daily-it-library-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    try {
      const incoming = parseLibrary(JSON.parse(await file.text()));
      if (!incoming) throw new Error("unsupported");
      update((current) => mergeLibraries(current, incoming));
      toast.success(`북마크 ${Object.keys(incoming.bookmarks).length}건, 읽음 ${Object.keys(incoming.read).length}건을 합쳤습니다.`);
    } catch {
      toast.error("가져올 수 없는 파일입니다 (버전 1 JSON만 지원).");
    } finally {
      if (input.current) input.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-muted-foreground">
          북마크 {saved.length}건 · 읽음 {Object.keys(library.read).length}건 — 이 브라우저에만 저장됩니다.
        </p>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" onClick={download}>
            <Download className="size-4" /> 내보내기
          </Button>
          <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
            <Upload className="size-4" /> 가져오기
          </Button>
          <input ref={input} type="file" accept="application/json,.json" className="hidden" aria-label="서재 JSON 파일" onChange={(e) => upload(e.target.files?.[0])} />
        </div>
      </div>
      {saved.length === 0 ? (
        <EmptyState title="저장한 기사가 없습니다" description="기사 카드의 북마크 아이콘을 누르면 여기에 모입니다." />
      ) : (
        <ul className="divide-y rounded-xl border">
          {saved.map((item) => (
            <li key={item.id} className="flex items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <a href={item.url} target="_blank" rel="noopener noreferrer" className="line-clamp-2 font-medium hover:underline">
                  {item.title} <ExternalLink className="inline size-3 text-muted-foreground" aria-hidden />
                </a>
                <p className="text-xs text-muted-foreground">
                  {item.source_name} · {formatDateTime(item.saved_at)} 저장
                </p>
              </div>
              <Button variant="ghost" size="icon" aria-label="북마크 삭제" onClick={() => toggleBookmark(item)}>
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
