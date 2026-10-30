import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';
import * as path from 'node:path';

const API = 'http://127.0.0.1:8000';
const root = path.resolve(__dirname, '..');
const fixtures = path.join(__dirname, 'fixtures');
const uploadButton = 'Upload & reconcile';

// Tests share one database, so they run in order.
test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  // 1,000 synthetic invoices -> 12 rules x 5 injected anomalies = 60 exceptions.
  execSync(
    `python -c "from app import generator; from datetime import date; generator.write_csvs(generator.generate(n=1000, seed=1, as_of=date.today()), 'e2e/fixtures')"`,
    { cwd: root },
  );
  // Loads the vendor master and tax rates that the uploaded CSVs refer to.
  const res = await request.post(`${API}/data/generate?n=1000`);
  expect(res.ok()).toBeTruthy();
});

test('API root redirects to the docs page', async ({ request }) => {
  const res = await request.get(`${API}/`);
  expect(res.ok()).toBeTruthy();
  expect(res.url()).toContain('/docs');
});

test('upload two CSVs and reconcile', async ({ page }) => {
  await page.goto('/upload');
  const inputs = page.locator('input[type=file]');
  await inputs.nth(0).setInputFiles(path.join(fixtures, 'invoices.csv'));
  await inputs.nth(1).setInputFiles(path.join(fixtures, 'payments.csv'));
  await page.getByRole('button', { name: uploadButton }).click();
  await expect(page.getByText('Loaded 1000 invoices')).toBeVisible();
  await expect(page.getByText('60 exceptions found')).toBeVisible();
});

test('summary lists all 12 rules with 5 findings each', async ({ page }) => {
  await page.goto('/summary');
  await expect(page.getByRole('heading', { name: /1000 invoices/ })).toBeVisible();
  await expect(page.locator('tr')).toHaveCount(13); // header + 12 rules
  await expect(page.getByRole('row', { name: /OVERPAID MEDIUM 5/ })).toBeVisible();
});

test('exceptions: rule filter and paging', async ({ page }) => {
  await page.goto('/exceptions');
  await expect(page.getByText('60 results · page 1')).toBeVisible();
  await page.locator('select').selectOption('OVERPAID');
  await expect(page.getByText('5 results · page 1')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Next' })).toBeDisabled();
  await page.locator('select').selectOption('');
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText('page 2')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prev' })).toBeEnabled();
});

test('malformed CSV shows a validation error and keeps existing data', async ({ page, request }) => {
  await page.goto('/upload');
  const inputs = page.locator('input[type=file]');
  await inputs.nth(0).setInputFiles({
    name: 'bad.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('invoice_no\nINV-1\n'),
  });
  await inputs.nth(1).setInputFiles(path.join(fixtures, 'payments.csv'));
  await page.getByRole('button', { name: uploadButton }).click();
  await expect(page.getByText(/missing columns/)).toBeVisible();
  const summary = await (await request.get(`${API}/summary`)).json();
  expect(summary.invoices).toBe(1000); // the failed upload did not wipe the data
});
