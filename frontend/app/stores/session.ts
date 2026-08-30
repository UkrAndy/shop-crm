import { defineStore } from 'pinia'

import type { OrganizationPublic, SessionPublic, UserPublic } from '~/types/api'

/**
 * Who is logged in and which organization they are working in.
 *
 * Hydrated on the **server** (see `plugins/session.ts`) and transferred in the
 * Nuxt payload, so the client starts out already knowing the answer. That is
 * what keeps a protected page from flashing the login screen on reload.
 *
 * The active organization is *not* kept here as the source of truth — it lives
 * on the session row in the database. This store mirrors it for rendering; the
 * server decides.
 */
export const useSessionStore = defineStore('session', () => {
  // Captured here, during store setup, while a Nuxt context still exists.
  // Actions run after `await`, where it does not.
  const api = createApiClient()

  const user = ref<UserPublic | null>(null)
  const organizations = ref<OrganizationPublic[]>([])
  const activeOrganizationId = ref<string | null>(null)
  const hydrated = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const activeOrganization = computed(
    () => organizations.value.find(item => item.id === activeOrganizationId.value) ?? null,
  )

  function reset() {
    user.value = null
    organizations.value = []
    activeOrganizationId.value = null
  }

  function apply(session: SessionPublic) {
    user.value = session.user
    activeOrganizationId.value = session.active_organization_id
  }

  async function loadOrganizations() {
    organizations.value = await api<OrganizationPublic[]>('/organizations')
  }

  /**
   * Resolve the session once per page load.
   *
   * A 401 here is the normal anonymous case, not an error worth surfacing, so
   * it resets quietly. Guarded by `hydrated` because the payload already
   * carries the server's answer — refetching on the client would defeat SSR.
   */
  async function hydrate() {
    if (hydrated.value) return
    try {
      apply(await api<SessionPublic>('/auth/me'))
      await loadOrganizations()
    }
    catch {
      reset()
    }
    hydrated.value = true
  }

  async function login(email: string, password: string) {
    apply(await api<SessionPublic>('/auth/login', {
      method: 'POST',
      body: { email, password },
    }))
    await loadOrganizations()
    hydrated.value = true
  }

  async function logout() {
    try {
      // 204 No Content — nothing to parse, so the response type is `unknown`
      // rather than `void`, which TypeScript only allows as a return type.
      await api<unknown>('/auth/logout', { method: 'POST' })
    }
    finally {
      // Local state is cleared even if the call failed: leaving the UI looking
      // logged in after the user asked to leave is the worse outcome, and the
      // cookie is what actually authorizes anything.
      reset()
    }
  }

  async function setActiveOrganization(organizationId: string) {
    const organization = await api<OrganizationPublic>('/organizations/active', {
      method: 'POST',
      body: { organization_id: organizationId },
    })
    activeOrganizationId.value = organization.id
  }

  return {
    user,
    organizations,
    activeOrganizationId,
    hydrated,
    isAuthenticated,
    activeOrganization,
    hydrate,
    login,
    logout,
    setActiveOrganization,
  }
})
