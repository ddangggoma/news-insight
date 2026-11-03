import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { linkModelAlias } = vi.hoisted(() => ({ linkModelAlias: vi.fn(async () => ({ ok: true })) }));
vi.mock("@/app/console/actions", () => ({ linkModelAlias }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LinkModelForm } from "@/components/console/benchmark-forms";
import type { UnmatchedModel } from "@/lib/types";

const MODEL: UnmatchedModel = { model_raw: "Claude Opus 5 (High)", org: "Anthropic", sites: ["lmarena"], last_seen: "2026-11-03T03:30:00Z" };

describe("LinkModelForm", () => {
  it("links the site's spelling to the edited model name", async () => {
    render(<LinkModelForm model={MODEL} />);
    fireEvent.change(screen.getByLabelText("Claude Opus 5 (High) 모델 이름"), { target: { value: " Claude Opus 5 " } });
    fireEvent.click(screen.getByRole("button", { name: /연결/ }));
    await waitFor(() => expect(linkModelAlias).toHaveBeenCalledWith("Claude Opus 5 (High)", "Claude Opus 5", "Anthropic"));
  });

  it("does not submit an empty name", () => {
    render(<LinkModelForm model={MODEL} />);
    fireEvent.change(screen.getByLabelText("Claude Opus 5 (High) 모델 이름"), { target: { value: "  " } });
    expect(screen.getByRole("button", { name: /연결/ })).toBeDisabled();
  });
});
