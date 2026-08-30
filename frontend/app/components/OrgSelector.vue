<script setup lang="ts">
const session = useSessionStore()

const pending = ref(false)
const error = ref<string | null>(null)

// Writes through the API rather than mutating local state: the active
// organization is the server's decision, and the store only mirrors it.
const selected = computed({
  get: () => session.activeOrganizationId,
  set: (value: string | null) => {
    if (value) void select(value)
  },
})

async function select(organizationId: string) {
  pending.value = true
  error.value = null
  try {
    await session.setActiveOrganization(organizationId)
  }
  catch (caught) {
    error.value = apiErrorMessage(caught, 'Не вдалося змінити організацію.')
  }
  finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label for="org-selector" class="text-sm font-medium">Організація</label>

    <Select
      v-model="selected"
      input-id="org-selector"
      data-testid="org-selector"
      :options="session.organizations"
      option-label="name"
      option-value="id"
      :loading="pending"
      placeholder="Оберіть організацію"
      class="w-full"
    />

    <small v-if="error" data-testid="org-selector-error" class="text-red-600">{{ error }}</small>
  </div>
</template>
