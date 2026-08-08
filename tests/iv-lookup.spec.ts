// tests/iv-lookup.spec.ts
import { test, expect } from '@playwright/test';
const cpCases = [
  { cp: '1900', note: '範囲内' },
  { cp: '9999', note: '範囲外' },
];
for (const c of cpCases) {
 test('ギャラドス IV逆引き CP=' + c.cp + '（' + c.note + '）', async ({ page }) =>  {
    await page.goto('/index.html');
    await page.locator('#scopeAll').click();
    await page.locator('#q').fill('ギャラドス');
    // 行をクリックして詳細画面を開く
    await page.locator('#list .row').first().click();
    await expect(page.locator('#sheet')).toBeVisible();
    // 詳細画面の最初の数値入力欄（＝CP欄）に値を入れる
    await page.locator('#sheet').getByRole('spinbutton').first().fill(c.cp);
    // 何らかの判定結果が表示されること
    await expect(page.locator('#sheet .verdict')).toBeVisible();
  });
}

