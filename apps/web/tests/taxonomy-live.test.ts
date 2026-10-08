import { describe, expect, it } from "vitest";

import { FIELD_LABEL, SIGNAL_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import { NODE_LABEL, applyTaxonomy, nodeOptions, type SchemeView } from "@/lib/taxonomy-live";

const tech: SchemeView = {
  key: "technology",
  name: "기술",
  structure: "tree",
  min_labels: 0,
  max_labels: 2,
  llm_depth: 2,
  level_names: [],
  uses: [],
  nodes: [
    { id: 1, key: "ai", label: "AI·에이전트", parent_id: null, depth: 1, status: "active", sort: 0 },
    { id: 2, key: "ai__ai_agents", label: "AI 에이전트(개편)", parent_id: 1, depth: 2, status: "active", sort: 0 },
    { id: 3, key: "coding-agent", label: "코딩 에이전트", parent_id: 2, depth: 3, status: "active", sort: 0 },
  ],
};

describe("live taxonomy labels", () => {
  it("updates the shared label records in place and keeps keys that left", () => {
    const keptOld = THEME_LABEL["semis__ap_soc_npu"];
    applyTaxonomy({
      revision: 7,
      schemes: [tech, { ...tech, key: "signal_type", structure: "list", nodes: [{ id: 9, key: "launch", label: "출시", parent_id: null, depth: 1, status: "active", sort: 0 }] }],
    });
    expect(FIELD_LABEL.ai).toBe("AI·에이전트");
    expect(THEME_LABEL.ai__ai_agents).toBe("AI 에이전트(개편)");
    expect(THEME_LABEL.semis__ap_soc_npu).toBe(keptOld);
    expect(SIGNAL_LABEL.launch).toBe("출시");
    expect(NODE_LABEL["technology:coding-agent"]).toBe("코딩 에이전트");
  });

  it("lists nodes of any depth parents first", () => {
    expect(nodeOptions(tech).map((o) => `${o.depth}:${o.value}`)).toEqual([
      "1:technology:ai",
      "2:technology:ai__ai_agents",
      "3:technology:coding-agent",
    ]);
  });
});
