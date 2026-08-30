<script setup lang="ts">
const model = defineModel<string | null>({ required: true })
const props = defineProps<{ readonly?: boolean, readonlyName?: string }>()

const { data: counterparties } = useCounterparties()
const createCounterparty = useCreateCounterparty()

const newName = ref('')
const adding = ref(false)
const error = ref<string | null>(null)

const options = computed(() => counterparties.value ?? [])

async function addSupplier() {
  const name = newName.value.trim()
  if (!name) return

  error.value = null
  try {
    const created = await createCounterparty.mutateAsync(name)
    model.value = created.id
    newName.value = ''
    adding.value = false
  }
  catch (caught) {
    // `counterparty_name_taken` is the common case and reads better than the
    // generic fallback, so the server's own message is shown as-is.
    error.value = apiErrorMessage(caught, 'Не вдалося створити постачальника.')
  }
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label for="receipt-supplier" class="text-sm font-medium">Постачальник</label>

    <span v-if="props.readonly" data-testid="receipt-supplier-readonly">
      {{ props.readonlyName ?? '—' }}
    </span>

    <template v-else>
      <div class="flex items-center gap-2">
        <Select
          v-model="model"
          input-id="receipt-supplier"
          data-testid="receipt-supplier"
          :options="options"
          option-label="name"
          option-value="id"
          filter
          placeholder="Оберіть постачальника"
          class="flex-1"
        />
        <Button
          data-testid="supplier-add-toggle"
          label="Новий"
          severity="secondary"
          size="small"
          @click="adding = !adding"
        />
      </div>

      <div v-if="adding" class="mt-2 flex items-center gap-2">
        <InputText
          v-model="newName"
          data-testid="supplier-new-name"
          placeholder="Назва постачальника"
          class="flex-1"
          @keyup.enter="addSupplier"
        />
        <Button
          data-testid="supplier-new-save"
          label="Додати"
          size="small"
          :loading="createCounterparty.isPending.value"
          @click="addSupplier"
        />
      </div>

      <small v-if="error" data-testid="supplier-error" class="text-red-600">{{ error }}</small>
    </template>
  </div>
</template>
