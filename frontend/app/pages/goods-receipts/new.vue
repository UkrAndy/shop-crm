<script setup lang="ts">
import type { DraftLine } from '~/components/ReceiptLineEditor.vue'

const createReceipt = useCreateGoodsReceipt()

const counterpartyId = ref<string | null>(null)
const lines = ref<DraftLine[]>([])
const editor = useTemplateRef('editor')
const formError = ref<string | null>(null)

async function save() {
  formError.value = null

  if (!counterpartyId.value) {
    formError.value = 'Оберіть постачальника.'
    return
  }

  try {
    const created = await createReceipt.mutateAsync({
      counterparty_id: counterpartyId.value,
      lines: editor.value?.toPayload() ?? [],
    })
    await navigateTo(`/goods-receipts/${created.id}`)
  }
  catch (error) {
    formError.value = apiErrorMessage(error, 'Не вдалося зберегти надходження.')
  }
}
</script>

<template>
  <main class="mx-auto flex max-w-3xl flex-col gap-5 p-8">
    <h1 data-testid="receipt-title" class="text-2xl font-semibold">
      Нове надходження
    </h1>

    <ReceiptSupplierPicker v-model="counterpartyId" />

    <ReceiptLineEditor ref="editor" v-model="lines" />

    <Message v-if="formError" data-testid="receipt-error" severity="error" :closable="false">
      {{ formError }}
    </Message>

    <div class="flex justify-end gap-2">
      <Button
        label="Скасувати"
        severity="secondary"
        @click="navigateTo('/goods-receipts')"
      />
      <Button
        data-testid="receipt-save"
        label="Зберегти чернетку"
        :loading="createReceipt.isPending.value"
        @click="save"
      />
    </div>
  </main>
</template>
