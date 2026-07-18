# Shellie eslint fallback configs (flat config, ESLint 9+)

Used by `read_lint` when a project has no local eslint config.

| File | Use for |
|------|---------|
| `eslint.script.mjs` | Classic browser JS / default `<script>` |
| `eslint.module.mjs` | `import`/`export` or `<script type="module">` |
| `eslint.jsx.mjs` | `.jsx` (JSX parse + light rules; no React plugin) |
| `browser_globals.mjs` | Shared globals + light rules (imported by the above) |

No TypeScript fallback here — `.ts`/`.tsx` use the project's eslint config and/or `tsc`.
