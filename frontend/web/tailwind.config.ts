import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        status: {
          queued: '#64748b',
          inflight: '#0ea5e9',
          processing: '#f59e0b',
          complete: '#22c55e',
          failed: '#ef4444',
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
