import { expect, test } from "@playwright/test";

import { STATE } from "./accounts";

// Plan 15-5: the console's taxonomy workspace on the seeded schemes.
test.describe("taxonomy workspace", () => {
  test.use({ storageState: STATE.admin });

  test("renames a node through a previewed change set and shows it in the history", async ({ page }) => {
    await page.goto("/console/taxonomy");
    await expect(page.getByRole("heading", { level: 1, name: "분류 체계" })).toBeVisible();
    const tree = page.getByRole("tree", { name: "기술 트리" });
    await tree.getByRole("button", { name: /frontier$/ }).click();
    await page.getByLabel("이름", { exact: true }).fill("미래 기술(E2E)");
    await page.getByRole("button", { name: "수정을 변경에 추가" }).click();
    const draft = page.getByRole("region", { name: "변경 초안" });
    await expect(draft).toContainText("이름 변경: 미래 기술 → 미래 기술(E2E)");
    await draft.getByRole("button", { name: "미리보기" }).click();
    await expect(page.getByLabel("미리보기 결과")).toContainText("재분류 없음");
    await draft.getByRole("button", { name: "적용" }).click();
    await expect(page.getByLabel("적용 결과")).toContainText("리비전 #");
    await page.getByRole("tab", { name: "이력" }).click();
    await expect(page.getByText("이름 변경: 미래 기술(E2E) → 미래 기술(E2E)").or(page.getByText(/이름 변경: .* → 미래 기술\(E2E\)/)).first()).toBeVisible();
  });

  test("adds a deeper node without reclassification", async ({ page }) => {
    await page.goto("/console/taxonomy");
    const tree = page.getByRole("tree", { name: "기술 트리" });
    await page.getByLabel("노드 검색").fill("양자");
    await tree.getByRole("button", { name: /frontier__quantum$/ }).click();
    await page.getByRole("button", { name: "하위 추가", exact: true }).click();
    await page.getByLabel("새 노드 이름").fill("양자 센서");
    await page.getByLabel("새 노드 별칭").fill("quantum sensor, 양자센서");
    await page.getByRole("button", { name: "추가를 변경에 넣기" }).click();
    const draft = page.getByRole("region", { name: "변경 초안" });
    await draft.getByRole("button", { name: "미리보기" }).click();
    await expect(page.getByLabel("미리보기 결과")).toContainText("재분류 없음");
    await draft.getByRole("button", { name: "비우기" }).click();
    await expect(draft).toHaveCount(0);
  });
});
