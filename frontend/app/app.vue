<script setup lang="ts">
/**
 * Marks the document once Vue has taken over the server-rendered markup.
 *
 * The E2E suite waits for this before typing. Filling an input before hydration
 * writes to the DOM only — Vue then re-renders from its own (empty) state and
 * the value vanishes, which surfaces as a form that submits blank for no
 * visible reason. One attribute is a cheap price for not chasing that again.
 */
onMounted(() => {
  document.documentElement.dataset.hydrated = 'true'
})
</script>

<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtPage />
  </div>
</template>
