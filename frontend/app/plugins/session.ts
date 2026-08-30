/**
 * Resolves the session before any route middleware runs.
 *
 * Nuxt runs plugins ahead of middleware, so by the time `auth.global.ts` asks
 * whether the visitor is authenticated, the answer is already known — on the
 * server as well as the client. Pinia state travels in the payload, so the
 * client does not repeat the request and the page never renders as anonymous
 * before correcting itself.
 */
export default defineNuxtPlugin(async (nuxtApp) => {
  const session = useSessionStore(nuxtApp.$pinia as never)
  await session.hydrate()
})
