/**
 * Shellie eslint fallback — ES modules (sourceType: "module").
 * Use for import/export or <script type="module">.
 */
import { browserGlobals, lightRules } from "./browser_globals.mjs";

export default [
  {
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: browserGlobals,
    },
    rules: lightRules,
  },
];
