import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/tests/**/*.test.ts'],
    environment: 'node',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: [
        'src/services/**',
        'src/tools/**',
        'src/main/httpServer.ts',
        'src/main/ipcHandlers.ts',
        'src/main/window.ts',
        'src/main/validation.ts',
        'src/utils/**',
        'src/renderer/logic/**',
        'src/renderer/ExpressionController.ts',
        'src/renderer/AnimationController.ts',
      ],
      thresholds: { statements: 100, branches: 100, functions: 100, lines: 100 },
    },
  },
});
