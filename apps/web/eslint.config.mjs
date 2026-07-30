import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Playwright artefacts.
    "playwright-report/**",
    "test-results/**",
    "e2e/.auth/**",
  ]),
  {
    // Acceptance tests are Node programs, not React. The React rules produce
    // only false positives here - most visibly, Playwright's fixture `use`
    // callback is read as React's `use` hook. TypeScript still type-checks
    // these files, which is where their real safety comes from.
    files: ["e2e/**/*.ts", "playwright.config.ts"],
    rules: {
      "react-hooks/rules-of-hooks": "off",
    },
  },
]);

export default eslintConfig;
