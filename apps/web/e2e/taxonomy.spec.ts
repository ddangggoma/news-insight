import { expect, type Locator, type Page, test } from "@playwright/test";

import { STATE } from "./accounts";

/** An HTML5 drag from one tree row to another, landing at `y` (0..1) of the target row's height.
 * The events are dispatched in the page (Playwright's mouse-driven drag stalls on this tree). */
async function drag(page: Page, source: Locator, target: Locator, y: number) {
  await source.scrollIntoViewIfNeeded();
  await target.scrollIntoViewIfNeeded();
  const from = await source.elementHandle();
  const to = await target.elementHandle();
  await page.evaluate(
    async ([src, dst, at]) => {
      const transfer = new DataTransfer();
      const box = (dst as HTMLElement).getBoundingClientRect();
      const point = { clientX: box.left + 40, clientY: box.top + box.height * (at as number) };
      const fire = (el: Element, type: string, extra = {}) =>
        el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: transfer, ...extra }));
      fire(src as Element, "dragstart");
      await new Promise((r) => setTimeout(r, 50)); // React commits the dragging state
      fire(dst as Element, "dragenter", point);
      fire(dst as Element, "dragover", point);
      await new Promise((r) => setTimeout(r, 50));
      fire(dst as Element, "dragover", point);
      fire(dst as Element, "drop", point);
      fire(src as Element, "dragend");
    },
    [from, to, y] as const,
  );
}

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

  test("drags a node inside another and between rows, shows the move, previews the impact", async ({ page }) => {
    await page.goto("/console/taxonomy");
    const tree = page.getByRole("tree", { name: "기술 트리" });
    await page.getByLabel("노드 검색").fill("양자");
    const quantum = tree.locator('[data-node-key="frontier__quantum"]');
    await page.getByLabel("노드 검색").fill("");
    const semis = tree.locator('[data-node-key="semis"]');
    await drag(page, quantum, semis, 0.5);
    const draft = page.getByRole("region", { name: "변경 초안" });
    await expect(draft).toContainText(/이동: .* → 반도체/);
    await expect(tree.locator('[data-node-key="frontier__quantum"]')).toContainText("이동 예정");

    // the top edge of a top-level row: before it, as a top-level node (2 -> 1)
    const ai = tree.locator('[data-node-key="ai"]');
    await drag(page, tree.locator('[data-node-key="frontier__quantum"]'), ai, 0.1);
    await expect(draft).toContainText(/이동: .* → 최상위 \(.* 앞\)/);
    await draft.getByRole("button", { name: "미리보기" }).click();
    await expect(page.getByLabel("미리보기 결과")).toContainText("2단계 → 1단계");
    await draft.getByRole("button", { name: "비우기" }).click();
  });
});
