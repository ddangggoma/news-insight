import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const actOnUser = vi.fn();
const resetUserPassword = vi.fn();
vi.mock("@/app/console/users/actions", () => ({ actOnUser, resetUserPassword, setUserRole: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { UserActions } = await import("@/components/console/user-actions");
const { toast } = await import("sonner");

const base = { id: 7, username: "reader.one", name: "김독자", role: "reader" as const, locked: false };

function buttons(): string[] {
  return screen.getAllByRole("button").map((button) => button.textContent ?? "");
}

beforeEach(() => {
  actOnUser.mockReset();
  resetUserPassword.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("UserActions", () => {
  it("offers approve and reject for a pending sign-up", () => {
    render(<UserActions user={{ ...base, status: "pending" }} />);
    expect(buttons()).toEqual(["승인", "거절"]);
  });

  it("manages an active account: role, suspension, unlock and password reset", () => {
    render(<UserActions user={{ ...base, status: "active", locked: true }} />);
    expect(buttons()).toEqual(["관리자로 변경", "정지", "잠금 해제", "비밀번호 초기화"]);
  });

  it("approves and reports the API's refusal", async () => {
    actOnUser.mockResolvedValue({ ok: false, error: "지금 상태에서는 할 수 없는 작업입니다." });
    render(<UserActions user={{ ...base, status: "pending" }} />);
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("지금 상태에서는 할 수 없는 작업입니다."));
    expect(actOnUser).toHaveBeenCalledWith(7, "approve");
  });

  it("shows a reset password once in a dialog", async () => {
    resetUserPassword.mockResolvedValue({ ok: true, temporaryPassword: "Tmp-abc123xyz789" });
    render(<UserActions user={{ ...base, status: "active" }} />);
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 초기화" }));
    expect(await screen.findByTestId("temporary-password")).toHaveTextContent("Tmp-abc123xyz789");
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByTestId("temporary-password")).not.toBeInTheDocument());
  });
});
