import type { ApiErrorResponse } from '~/types/api'

export type ApiClient = ReturnType<typeof $fetch.create>

/**
 * Builds a fetch client bound to the backend, with the session cookie attached
 * on both sides of SSR.
 *
 * **Must be called inside a Nuxt context** — a plugin, middleware, or a store's
 * setup function — because `useRuntimeConfig` and `useRequestHeaders` need one.
 * It captures what it needs there and returns a plain function, so callers can
 * use it after an `await`, where the context is gone. Reading the config inside
 * each request instead throws `NUXT_E1001` on the second call of any action.
 *
 * The two sides need different things:
 * - **Browser:** `credentials: 'include'`, because the API is a different origin
 *   (port 8000 vs 3000) and cross-origin `fetch` omits cookies by default.
 * - **Nuxt server:** the outgoing request has no cookie jar, so the incoming
 *   browser cookie is forwarded by hand. Without this, SSR renders as an
 *   anonymous visitor and the page flashes the login screen after hydration —
 *   the failure the whole cookie-based design exists to avoid.
 *
 * Note that `localhost:3000` and `localhost:8000` are the *same site* (ports are
 * not part of a site), so `SameSite=Lax` is satisfied while CORS still applies.
 */
export function createApiClient(): ApiClient {
  const config = useRuntimeConfig()
  const cookie = import.meta.server ? useRequestHeaders(['cookie']).cookie : undefined

  return $fetch.create({
    baseURL: config.public.apiBase,
    credentials: 'include',
    headers: cookie ? { cookie } : undefined,
  })
}

/**
 * Pulls the message out of the shared error envelope.
 *
 * `$fetch` rejects with a `FetchError` whose `data` is the parsed body, so the
 * envelope survives. Anything without one is a transport or server failure and
 * gets the fallback rather than a misleading `[object Object]`.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const body = (error as { data?: ApiErrorResponse } | undefined)?.data
  return body?.error?.message ?? fallback
}

export function apiErrorCode(error: unknown): string | null {
  const body = (error as { data?: ApiErrorResponse } | undefined)?.data
  return body?.error?.code ?? null
}
