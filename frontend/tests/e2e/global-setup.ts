import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

/**
 * Brings the database to `head` and seeds deterministic accounts.
 *
 * Runs before the web servers start, so the backend never observes a
 * half-migrated schema. `uv` must be on PATH — it is, in CI via
 * `astral-sh/setup-uv`, and locally wherever `uv run` already works.
 */
function backend(...args: string[]) {
  execFileSync('uv', args, {
    cwd: fileURLToPath(new URL('../../../backend', import.meta.url)),
    stdio: 'inherit',
    // No `shell: true`: it concatenates arguments without escaping, which Node
    // flags as a security hazard (DEP0190). `uv` is a real executable, so it
    // resolves on PATH without one.
  })
}

export default function globalSetup() {
  backend('run', 'alembic', 'upgrade', 'head')
  backend('run', 'python', 'scripts/seed_dev.py')
}
