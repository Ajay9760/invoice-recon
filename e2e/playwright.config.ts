import { defineConfig } from '@playwright/test';

// Requires the API on :8000 and the Angular app on :4200 to be running.
export default defineConfig({
  testDir: '.',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://localhost:4200' },
});
