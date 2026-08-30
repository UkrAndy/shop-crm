/**
 * Redirects anonymous visitors to `/login`.
 *
 * Global with an explicit public allowlist, rather than opt-in per page: a page
 * added later without the right `definePageMeta` would otherwise be silently
 * public. Failing closed is worth the small ceremony of this list.
 *
 * This is user experience only. It is never authorization — every endpoint
 * enforces its own scope server-side (research §624), and a user who bypasses
 * this middleware still gets 401 and 403 from the API.
 */
const PUBLIC_ROUTES = new Set(['/login'])

export default defineNuxtRouteMiddleware((to) => {
  const session = useSessionStore()

  if (PUBLIC_ROUTES.has(to.path)) {
    // Already signed in? The login page has nothing to offer.
    return session.isAuthenticated ? navigateTo('/') : undefined
  }

  if (!session.isAuthenticated) {
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  }
})
