/**
 * Shellie eslint fallback — JSX parse + light rules (no React plugin).
 */
import { browserGlobals, lightRules } from "./browser_globals.mjs";

export default [
  {
    files: ["**/*.{js,jsx,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...browserGlobals,
        React: "readonly",
        JSX: "readonly",
      },
    },
    rules: lightRules,
  },
];
