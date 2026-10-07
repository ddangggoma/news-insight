import { expect, test as setup } from "@playwright/test";

import { ADMIN, READER, STATE, logIn } from "./accounts";

// Log the seeded accounts in once; the other specs start from these saved sessions.
for (const [account, file] of [
  [READER, STATE.reader],
  [ADMIN, STATE.admin],
] as const) {
  setup(`log in as ${account.username}`, async ({ page }) => {
    await logIn(page, account.username);
    await expect(page).toHaveURL(/\/$/);
    await page.context().storageState({ path: file });
  });
}
