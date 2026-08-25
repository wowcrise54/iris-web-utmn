import { test, expect } from '@playwright/test';

test.describe('Minimalist Base Styles', () => {
  test('should load Inter font correctly', async ({ page }) => {
    await page.goto('/dashboard');
    const bodyFont = await page.evaluate(() => 
      getComputedStyle(document.body).fontFamily
    );
    expect(bodyFont).toContain('Inter');
  });

  test('should apply correct base font size', async ({ page }) => {
    await page.goto('/dashboard');
    const fontSize = await page.evaluate(() => 
      getComputedStyle(document.body).fontSize
    );
    expect(fontSize).toBe('16px');
  });

  test('should have correct line height for body text', async ({ page }) => {
    await page.goto('/dashboard');
    const lineHeight = await page.evaluate(() => 
      getComputedStyle(document.body).lineHeight
    );
    expect(lineHeight).toBe('24px'); // 1.5 * 16px
  });

  test('should render headings with correct hierarchy', async ({ page }) => {
    await page.goto('/dashboard');
    const h1Element = await page.$('h1');
    if (h1Element) {
      const h1Size = await page.evaluate(() => 
        getComputedStyle(document.querySelector('h1')).fontSize
      );
      expect(h1Size).toBe('30px'); // text-3xl
    }
  });

  test('should apply correct spacing between elements', async ({ page }) => {
    await page.goto('/dashboard');
    const paragraphs = await page.locator('p').all();
    if (paragraphs.length >= 2) {
      const margin = await paragraphs[0].evaluate(el => 
        getComputedStyle(el).marginBottom
      );
      expect(margin).toBe('16px'); // space-4
    }
  });
});
