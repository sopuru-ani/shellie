/**
 * Shellie eslint fallback — classic browser scripts (sourceType: "script").
 * Used when the project has no eslint config. Flat config (ESLint 9+).
 */
import { browserGlobals, lightRules } from "./browser_globals.mjs";

export default [
  {
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: browserGlobals,
    },
    rules: lightRules,
  },
];
