import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("states the daily publication schedule", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Daily IT Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/07:00 KST 정시 발행/)).toBeInTheDocument();
  });
});
