<script setup lang="ts">
const config = useRuntimeConfig()

// Set during SSR and transferred in the payload, so the value below is proof
// the markup came from the server rather than from client-side hydration.
const renderedOn = useState<'server' | 'client'>('rendered-on', () =>
  import.meta.server ? 'server' : 'client',
)
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
    <h1 data-testid="app-title" class="text-2xl font-semibold">
      TestVasja — Inventory &amp; Accounting
    </h1>

    <p class="text-sm">
      Phase 1 scaffold. Rendered on:
      <strong data-testid="render-origin">{{ renderedOn }}</strong>
    </p>

    <p class="text-sm">
      API base:
      <code data-testid="api-base">{{ config.public.apiBase }}</code>
    </p>

    <div>
      <Button label="PrimeVue is wired" severity="secondary" />
    </div>
  </main>
</template>
