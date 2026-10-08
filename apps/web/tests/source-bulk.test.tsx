import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const bulkSources = vi.fn();
vi.mock("@/app/console/actions", () => ({ bulkSources }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { BulkBar, BulkCheckbox, BulkSelection } = await import("@/components/console/source-bulk");
const { toast } = await import("sonner");

function view() {
  return render(
    <BulkSelection>
      <BulkBar pageKeys={["a", "b"]} />
      <BulkCheckbox sourceKey="a" />
      <BulkCheckbox sourceKey="b" />
    </BulkSelection>,
  );
}

beforeEach(() => {
  bulkSources.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("source bulk actions", () => {
  it("needs a selection and a reason before pausing", async () => {
    bulkSources.mockResolvedValue({ ok: true, done: ["a"], failed: [] });
    view();
    const apply = screen.getByRole("button", { name: "적용" });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "a 선택" }));
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "사유" }), { target: { value: "정리" } });
    fireEvent.click(apply);
    await waitFor(() => expect(bulkSources).toHaveBeenCalledWith(["a"], "pause", "정리"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("selects the whole page and retires after a confirmation, reporting failures", async () => {
    bulkSources.mockResolvedValue({ ok: true, done: ["a"], failed: [{ key: "b", error: "unknown source" }] });
    view();
    fireEvent.click(screen.getByRole("checkbox", { name: "이 페이지 전체 선택" }));
    fireEvent.change(screen.getByRole("combobox", { name: "일괄 작업" }), { target: { value: "retire" } });
    fireEvent.change(screen.getByRole("textbox", { name: "사유" }), { target: { value: "레포 감시 중단" } });
    fireEvent.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(bulkSources).toHaveBeenCalledWith(["a", "b"], "retire", "레포 감시 중단"));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("b (unknown source)")));
  });
});
