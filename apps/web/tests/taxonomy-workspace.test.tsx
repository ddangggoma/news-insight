import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const previewChanges = vi.fn();
const applyChanges = vi.fn();
vi.mock("@/app/console/taxonomy/actions", () => ({ previewChanges, applyChanges, rollbackRevision: vi.fn(), nodeCards: vi.fn(async () => []) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { ChangeBar } = await import("@/components/console/taxonomy/change-bar");
const { TaxonomyTree } = await import("@/components/console/taxonomy/tree");
const { isInside, visibleIds } = await import("@/components/console/taxonomy/model");
const { describe: describeOp, suggestKey } = await import("@/lib/taxonomy-ops");

const node = (id: number, key: string, label: string, parent: number | null, depth: number) => ({
  id, key, label, parent_id: parent, depth, status: "active", sort: 0, definition: null, include_text: null, exclude_text: null, aliases: [] as string[], attrs: {}, merged_into_id: null, edited_in_console: false,
});
const nodes = [node(1, "ai", "AI", null, 1), node(2, "ai__agents", "AI 에이전트", 1, 2), node(3, "coding-agent", "코딩 에이전트", 2, 3), node(4, "semis", "반도체", null, 1)];
const scheme = { key: "technology", name: "기술", structure: "tree" as const, min_labels: 0, max_labels: 2, llm_depth: 2, level_names: ["분야", "테마", "기술"], uses: [], assign: ["llm" as const], description: null, nodes };
const label = (s: string, k: string) => nodes.find((n) => n.key === k)?.label ?? k;

beforeEach(() => {
  previewChanges.mockReset();
  applyChanges.mockReset();
});

describe("taxonomy ops and tree helpers", () => {
  it("describes operations with node names and suggests keys", () => {
    expect(describeOp({ op: "merge_node", scheme: "technology", key: "ai__agents", into: "ai" }, label)).toBe("통합: AI 에이전트 → AI");
    expect(describeOp({ op: "move_node", scheme: "technology", key: "coding-agent", parent: null }, label)).toBe("이동: 코딩 에이전트 → 최상위");
    expect(suggestKey(" 위성 직접통신 / D2D ")).toBe("위성-직접통신-d2d");
  });

  it("keeps ancestors of search hits and refuses moves into a subtree", () => {
    expect([...(visibleIds(nodes, "코딩") ?? [])].sort()).toEqual([1, 2, 3]);
    expect(visibleIds(nodes, " ")).toBeNull();
    expect(isInside(nodes, nodes[0], nodes[2])).toBe(true);
    expect(isInside(nodes, nodes[2], nodes[0])).toBe(false);
  });
});

describe("taxonomy workspace parts", () => {
  it("renders any depth, expands and selects", () => {
    const onSelect = vi.fn();
    render(<TaxonomyTree scheme={scheme} counts={{ "1": { own: 2, total: 10 } }} selected={null} onSelect={onSelect} onMove={vi.fn()} showInactive={false} />);
    expect(screen.getByRole("tree", { name: "기술 트리" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "AI 에이전트 펼치기" }));
    fireEvent.click(screen.getByRole("button", { name: /코딩 에이전트/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ key: "coding-agent" }));
    expect(screen.getByText("10 / 2")).toBeInTheDocument();
  });

  it("previews before it applies and shows the impact", async () => {
    const result = { revision_id: null, outcomes: [{ op: "merge_node", summary: "통합", cards: 5, requeued: 0, warnings: [] }], affected_cards: 5, requeued_cards: 0, eta_hours: null, prompt_tokens: 1800, prompt_over_budget: false, samples: [] };
    previewChanges.mockResolvedValue({ ok: true, result });
    applyChanges.mockResolvedValue({ ok: true, result: { ...result, revision_id: 9 } });
    const onClear = vi.fn();
    render(<ChangeBar ops={[{ op: "merge_node", scheme: "technology", key: "ai__agents", into: "ai" }]} label={label} onRemove={vi.fn()} onClear={onClear} />);
    expect(screen.getByRole("button", { name: "적용" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
    await waitFor(() => expect(screen.getByLabelText("미리보기 결과")).toHaveTextContent("영향 카드 5"));
    fireEvent.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(applyChanges).toHaveBeenCalled());
    await waitFor(() => expect(onClear).toHaveBeenCalled());
  });
});
