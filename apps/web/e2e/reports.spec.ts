import { expect, test } from "@playwright/test";

// plan 17 R1: a reader asks for a trend report; it waits in the queue for the host job (not run in E2E).
test.describe("trend reports", () => {
  test("requests a report on a topic and shows it waiting", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { level: 1, name: "동향 보고서" })).toBeVisible();
    await page.getByLabel("주제").fill("온디바이스 AI 칩 경쟁");
    await page.getByLabel(/정보·관점/).fill("삼성과 퀄컴의 NPU 경쟁을 중심으로");
    await page.getByLabel("근거 기간").selectOption("30");
    await page.getByRole("button", { name: "보고서 요청" }).click();

    await expect(page).toHaveURL(/\/reports\/\d+$/);
    await expect(page.getByRole("heading", { level: 1, name: "온디바이스 AI 칩 경쟁" })).toBeVisible();
    await expect(page.getByRole("status")).toContainText(/대기 중|작성 중/);

    await page.goto("/reports");
    await expect(page.getByRole("link", { name: /온디바이스 AI 칩 경쟁/ }).first()).toBeVisible();
  });
});
