<script setup lang="ts">
const session = useSessionStore()

// Set during SSR and carried in the payload, so the value below is proof the
// markup came from the server rather than from client-side hydration.
const renderedOn = useState<'server' | 'client'>('rendered-on', () =>
  import.meta.server ? 'server' : 'client',
)

const loggingOut = ref(false)

async function onLogout() {
  loggingOut.value = true
  try {
    await session.logout()
    await navigateTo('/login')
  }
  finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
    <h1 data-testid="app-title" class="text-2xl font-semibold">
      TestVasja — Inventory &amp; Accounting
    </h1>

    <p class="text-sm">
      Увійшли як
      <strong data-testid="current-user">{{ session.user?.email }}</strong>
    </p>

    <OrgSelector />

    <p class="text-sm">
      Активна організація:
      <strong data-testid="active-organization">
        {{ session.activeOrganization?.name ?? 'не обрано' }}
      </strong>
    </p>

    <div>
      <NuxtLink data-testid="nav-products" to="/products" class="text-sm underline">
        Товари →
      </NuxtLink>
    </div>

    <p class="text-xs text-gray-500">
      Phase 3. Rendered on:
      <span data-testid="render-origin">{{ renderedOn }}</span>
    </p>

    <div>
      <Button
        data-testid="logout"
        label="Вийти"
        severity="secondary"
        :loading="loggingOut"
        @click="onLogout"
      />
    </div>
  </main>
</template>
