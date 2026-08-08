import { test, expect } from '@playwright/test';

const cases = [
  { query: 'ピカチュウ', expect: 'ピカチュウ' },
  { query: 'ミュウツー', expect: 'ミュウツー' },
  { query: 'カイリュー', expect: 'カイリュー' },
  { query: 'ぎゃらどす', expect: 'ギャラドス' },
];

for (const c of cases) {
  test(`検索: ${c.query} → CP範囲が表示される`, async ({ page }) => {
    await page.goto('/index.html');
    await page.locator('#scopeAll').click();
    await page.locator('#q').fill(c.query);

    const firstRow = page.locator('#list .row').first();
    await expect(firstRow.locator('.nm')).toContainText(c.expect);
    await expect(firstRow.locator('.cprange')).toContainText(/\d+/);
  });
}
