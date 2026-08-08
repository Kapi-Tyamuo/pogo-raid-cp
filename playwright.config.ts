import { defineConfig } from '@playwright/test';

export default defineConfig({
  webServer: {
    command: 'python3 -m http.server 5173',
    url: 'http://localhost:5173/index.html',
    reuseExistingServer: !process.env.CI,
  },
  use: { baseURL: 'http://localhost:5173' },
});
