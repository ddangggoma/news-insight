"use client";

import { useEffect, useState, useTransition } from "react";

import { nodeCards } from "@/app/console/taxonomy/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatNumber, formatRelative } from "@/lib/format";
import { PRIORITY_LABEL, suggestKey, type TaxOp } from "@/lib/taxonomy-ops";

import { type ConsoleNode, type ConsoleScheme, type Counts, isInside, levelName, pathLabel } from "./model";
import { EmbeddingHelp } from "./embedding-help";
import { NodePicker } from "./node-picker";

type Mode = "child" | "move" | "merge" | "retire" | "split" | "relation" | null;
const SOURCE: Record<string, string> = { legacy: "LLM", llm: "LLM", rule: "규칙", derived: "파생", human: "사람" };

function Area({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block space-y-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={2} className="w-full rounded-md border bg-background px-2 py-1 text-sm" />
    </label>
  );
}

/** Edit one node and queue operations on it; nothing changes until the change set is applied. */
export function NodeInspector({
  scheme,
  schemes,
  node,
  counts,
  onAdd,
}: {
  scheme: ConsoleScheme;
  schemes: ConsoleScheme[];
  node: ConsoleNode;
  counts: Counts;
  onAdd: (op: TaxOp) => void;
}) {
  const [label, setLabel] = useState(node.label);
  const [definition, setDefinition] = useState(node.definition ?? "");
  const [include, setInclude] = useState(node.include_text ?? "");
  const [exclude, setExclude] = useState(node.exclude_text ?? "");
  const [aliases, setAliases] = useState(node.aliases.join(", "));
  const [mode, setMode] = useState<Mode>(null);
  const [childLabel, setChildLabel] = useState("");
  const [childAliases, setChildAliases] = useState("");
  const [requeue, setRequeue] = useState(false);
  const [parts, setParts] = useState("");
  const [targetScheme, setTargetScheme] = useState(schemes.find((s) => s.key !== scheme.key)?.key ?? scheme.key);
  const [cards, setCards] = useState<Awaited<ReturnType<typeof nodeCards>> | null>(null);
  const [, start] = useTransition();

  useEffect(() => {
    setLabel(node.label);
    setDefinition(node.definition ?? "");
    setInclude(node.include_text ?? "");
    setExclude(node.exclude_text ?? "");
    setAliases(node.aliases.join(", "));
    setMode(null);
    setCards(null);
    start(async () => setCards(await nodeCards(node.id).catch(() => [])));
  }, [node]);

  const base = { scheme: scheme.key, key: node.key };
  const childDepth = node.depth + 1;
  const childIsLlm = scheme.llm_depth ? childDepth <= scheme.llm_depth : true;
  const count = counts[String(node.id)];
  const split = (text: string) => text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);

  const saveEdits = () => {
    const op: TaxOp = { op: "update_node", ...base };
    if (label.trim() && label.trim() !== node.label) op.label = label.trim();
    if ((definition || null) !== node.definition) op.definition = definition || null;
    if ((include || null) !== node.include_text) op.include_text = include || null;
    if ((exclude || null) !== node.exclude_text) op.exclude_text = exclude || null;
    const nextAliases = split(aliases);
    if (nextAliases.join("|") !== node.aliases.join("|")) op.aliases = nextAliases;
    if (Object.keys(op).length > 3) onAdd(op);
  };

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <p className="text-xs text-muted-foreground">{pathLabel(scheme.nodes, node)}</p>
        <h2 className="text-lg font-semibold">{node.label}</h2>
        <p className="text-xs text-muted-foreground">
          {levelName(scheme, node.depth)} · 키 <span className="font-mono">{node.key}</span> · 30일 카드 {formatNumber(count?.total ?? 0)}
          {count && count.own !== count.total ? ` (이 노드 ${formatNumber(count.own)})` : ""}
          {scheme.llm_depth && node.depth <= scheme.llm_depth ? " · LLM이 고르는 깊이" : " · 규칙(별칭)으로 붙는 깊이"}
        </p>
      </header>

      <section className="space-y-2">
        <label className="block space-y-1 text-xs">
          <span className="text-muted-foreground">이름</span>
          <Input value={label} onChange={(event) => setLabel(event.target.value)} className="h-8" />
        </label>
        <Area label="정의 (프롬프트에 들어갑니다)" value={definition} onChange={setDefinition} />
        <div className="grid gap-2 sm:grid-cols-2">
          <Area label="포함 기준" value={include} onChange={setInclude} />
          <Area label="제외 기준" value={exclude} onChange={setExclude} />
        </div>
        <label className="block space-y-1 text-xs">
          <span className="text-muted-foreground">별칭 (쉼표로 구분, 카드 키워드와 맞으면 붙습니다)</span>
          <Input value={aliases} onChange={(event) => setAliases(event.target.value)} className="h-8" />
        </label>
        {scheme.key === "technology" ? (
          <label className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">카드화 우선순위</span>
            <select
              aria-label="카드화 우선순위"
              value={String(node.attrs.priority ?? 1)}
              onChange={(event) => onAdd({ op: "update_node", ...base, priority: Number(event.target.value) })}
              className="h-8 rounded-md border bg-background px-2 text-sm"
            >
              {Object.entries(PRIORITY_LABEL).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
            <span className="text-muted-foreground">
              {scheme.llm_depth && node.depth <= scheme.llm_depth ? "제목으로 예측한 테마·분야에 적용" : "제목에 이름·별칭이 나오면 적용"} · 제외는 카드화하지 않음
            </span>
          </label>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={saveEdits}>
            수정을 변경에 추가
          </Button>
          {node.status === "active" ? (
            <Button size="sm" variant="outline" onClick={() => onAdd({ op: "update_node", ...base, status: "deprecated" })}>
              비활성화
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => onAdd({ op: "update_node", ...base, status: "active" })}>
              다시 활성화
            </Button>
          )}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {(scheme.structure === "tree" ? (["child", "move", "merge", "retire", "split", "relation"] as const) : (["merge", "retire", "split", "relation"] as const)).map((m) => (
            <Button key={m} size="sm" variant={mode === m ? "default" : "outline"} onClick={() => setMode(mode === m ? null : m)}>
              {{ child: "하위 추가", move: "이동", merge: "통합", retire: "폐지", split: "분할", relation: "관계" }[m]}
            </Button>
          ))}
        </div>
        {mode === "child" ? (
          <div className="space-y-2 rounded-md border p-2">
            <Input value={childLabel} onChange={(event) => setChildLabel(event.target.value)} placeholder={`새 ${levelName(scheme, childDepth)} 이름`} aria-label="새 노드 이름" className="h-8" />
            <Input value={childAliases} onChange={(event) => setChildAliases(event.target.value)} placeholder="별칭 (쉼표로)" aria-label="새 노드 별칭" className="h-8" />
            {childIsLlm ? (
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={requeue} onChange={(event) => setRequeue(event.target.checked)} /> LLM 깊이입니다: 이 노드 아래 카드를 다시 분류
              </label>
            ) : (
              <p className="text-xs text-muted-foreground">LLM보다 깊은 노드: 별칭이 맞는 카드에 바로 붙고 재분류는 필요 없습니다.</p>
            )}
            <Button
              size="sm"
              disabled={!childLabel.trim()}
              onClick={() => {
                onAdd({ op: "create_node", scheme: scheme.key, key: suggestKey(childLabel) || `node-${Date.now()}`, label: childLabel.trim(), parent: node.key, aliases: split(childAliases), requeue: childIsLlm && requeue });
                setChildLabel("");
                setChildAliases("");
              }}
            >
              추가를 변경에 넣기
            </Button>
          </div>
        ) : null}
        {mode === "move" ? <NodePicker label="새 상위 노드" allowRoot nodes={scheme.nodes} exclude={(n) => isInside(scheme.nodes, node, n)} onPick={(parent) => onAdd({ op: "move_node", ...base, parent: parent?.key ?? null })} /> : null}
        {mode === "merge" ? <NodePicker label="합칠 대상" nodes={scheme.nodes} exclude={(n) => isInside(scheme.nodes, node, n)} onPick={(into) => into && onAdd({ op: "merge_node", ...base, into: into.key })} /> : null}
        {mode === "retire" ? (
          <div className="space-y-2">
            <Button size="sm" variant="outline" onClick={() => onAdd({ op: "retire_node", ...base })}>
              대체 없이 폐지 (라벨 삭제, 하위는 상위로)
            </Button>
            <NodePicker label="대체 노드" nodes={scheme.nodes} exclude={(n) => isInside(scheme.nodes, node, n)} onPick={(to) => to && onAdd({ op: "retire_node", ...base, replacement: to.key })} />
          </div>
        ) : null}
        {mode === "split" ? (
          <div className="space-y-2 rounded-md border p-2">
            <Area label="나눌 노드 이름 (한 줄에 하나, 2개 이상)" value={parts} onChange={setParts} />
            <Button
              size="sm"
              disabled={split(parts).length < 2}
              onClick={() => onAdd({ op: "split_node", ...base, parts: split(parts).map((p) => ({ key: suggestKey(p), label: p })) })}
            >
              분할을 변경에 넣기 (해당 카드 재분류)
            </Button>
          </div>
        ) : null}
        {mode === "relation" ? (
          <div className="space-y-2 rounded-md border p-2">
            <p className="text-xs text-muted-foreground">이 노드(와 하위)의 카드에 다른 체계의 노드를 자동으로 붙입니다(파생).</p>
            <select value={targetScheme} onChange={(event) => setTargetScheme(event.target.value)} aria-label="대상 체계" className="h-8 rounded-md border bg-background px-2 text-sm">
              {schemes.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
            <NodePicker
              label="대상 노드"
              nodes={schemes.find((s) => s.key === targetScheme)?.nodes ?? []}
              onPick={(to) => to && onAdd({ op: "add_relation", from_scheme: scheme.key, from_key: node.key, to_scheme: targetScheme, to_key: to.key })}
            />
          </div>
        ) : null}
      </section>

      <EmbeddingHelp key={node.id} node={node} />

      <section className="space-y-1.5">
        <h3 className="text-sm font-semibold">최근 카드</h3>
        {cards === null ? (
          <p className="text-xs text-muted-foreground">불러오는 중…</p>
        ) : cards.length ? (
          <ul className="space-y-1 text-sm">
            {cards.map((card) => (
              <li key={card.item_id} className="flex gap-2">
                <span className="w-10 shrink-0 text-[11px] text-muted-foreground">{SOURCE[card.source] ?? card.source}</span>
                <a href={`/console/items/${card.item_id}`} className="min-w-0 flex-1 truncate hover:underline">
                  {card.title}
                </a>
                <span className="shrink-0 text-[11px] text-muted-foreground">{formatRelative(card.first_seen_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">이 노드에 붙은 카드가 없습니다.</p>
        )}
      </section>
    </div>
  );
}
