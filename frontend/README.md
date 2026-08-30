# frontend — Nuxt 4 (SSR)

Part of the TestVasja pnpm workspace. Install from the **repository root**
(`pnpm install`), not from this directory.

| Command | Purpose |
|---|---|
| `pnpm dev` | Dev server on http://localhost:3000 (SSR) |
| `pnpm build` | Production build into `.output/` |
| `pnpm preview` | Serve the production build |
| `pnpm lint` | ESLint (flat config via `@nuxt/eslint`) |
| `pnpm typecheck` | `vue-tsc` in strict mode |

Copy `.env.example` to `.env` to point the app at a backend other than
`http://localhost:8000/api/v1` (`NUXT_PUBLIC_API_BASE`).

Setup, prerequisites, and the full quality-gate list live in the root
[`README.md`](../README.md); workflow rules live in [`AGENTS.md`](../AGENTS.md).
