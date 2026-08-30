<script setup lang="ts">
import type { DraftLine } from '~/components/ReceiptLineEditor.vue'

const route = useRoute()
const receiptId = computed(() => String(route.params.id))

const { data: receipt, isPending, isError, error, refetch } = useGoodsReceipt(receiptId)
const updateReceipt = useUpdateGoodsReceipt()

const counterpartyId = ref<string | null>(null)
const lines = ref<DraftLine[]>([])
const editor = useTemplateRef('editor')
const formError = ref<string | null>(null)
const conflict = ref(false)

const isPosted = computed(() => receipt.value?.status === 'posted')

/** Load the server's copy into the editor. Also the reload half of reload-and-retry. */
function hydrateForm() {
  if (!receipt.value) return
  counterpartyId.value = receipt.value.counterparty_id
  lines.value = receipt.value.lines.map(item => ({
    product_id: item.product_id,
    quantity: item.quantity,
    purchase_price: item.purchase_price,
  }))
  formError.value = null
  conflict.value = false
}

watch(receipt, hydrateForm, { immediate: true })

async function save() {
  if (!receipt.value) return
  formError.value = null
  conflict.value = false

  try {
    await updateReceipt.mutateAsync({
      id: receipt.value.id,
      payload: {
        version: receipt.value.version,
        counterparty_id: counterpartyId.value ?? undefined,
        lines: editor.value?.toPayload() ?? [],
      },
    })
    await refetch()
  }
  catch (caught) {
    const code = apiErrorCode(caught)
    if (code === 'version_conflict') {
      // Same contract as products: say what happened and offer a reload. The
      // user's edits stay on screen until they decide.
      conflict.value = true
      return
    }
    formError.value = apiErrorMessage(caught, 'Не вдалося зберегти надходження.')
  }
}

async function reloadAndRetry() {
  await refetch()
  hydrateForm()
}
</script>

<template>
  <main class="mx-auto flex max-w-3xl flex-col gap-5 p-8">
    <div class="flex items-center justify-between gap-4">
      <h1 data-testid="receipt-title" class="text-2xl font-semibold">
        Надходження
      </h1>
      <Tag
        v-if="receipt"
        data-testid="receipt-status"
        :value="isPosted ? 'Проведено' : 'Чернетка'"
        :severity="isPosted ? 'success' : 'secondary'"
      />
    </div>

    <Message v-if="isError" data-testid="receipt-load-error" severity="error" :closable="false">
      {{ apiErrorMessage(error, 'Не вдалося завантажити надходження.') }}
    </Message>

    <ProgressSpinner v-else-if="isPending" style="width: 2rem; height: 2rem" />

    <template v-else-if="receipt">
      <p class="text-sm text-gray-600">
        Створив <strong data-testid="receipt-author">{{ receipt.created_by_email }}</strong>
      </p>

      <Message
        v-if="conflict"
        data-testid="receipt-conflict"
        severity="warn"
        :closable="false"
      >
        <p class="mb-2">
          Документ змінив хтось інший, поки ви редагували. Ваші зміни не збережено, щоб
          не перезаписати чужі.
        </p>
        <Button
          data-testid="receipt-conflict-reload"
          label="Перезавантажити та повторити"
          size="small"
          @click="reloadAndRetry"
        />
      </Message>

      <ReceiptSupplierPicker
        v-model="counterpartyId"
        :readonly="isPosted"
        :readonly-name="receipt.counterparty_name"
      />

      <ReceiptLineEditor ref="editor" v-model="lines" :readonly="isPosted" />

      <Message v-if="formError" data-testid="receipt-error" severity="error" :closable="false">
        {{ formError }}
      </Message>

      <!-- A posted document has no editing affordances at all: no inputs, no
           save button. The server refuses it too (409), but showing a control
           that cannot work is its own kind of bug. -->
      <div v-if="!isPosted" class="flex justify-end gap-2">
        <Button
          label="До списку"
          severity="secondary"
          @click="navigateTo('/goods-receipts')"
        />
        <Button
          data-testid="receipt-save"
          label="Зберегти"
          :loading="updateReceipt.isPending.value"
          :disabled="conflict"
          @click="save"
        />
      </div>
      <div v-else class="flex justify-end">
        <Button
          label="До списку"
          severity="secondary"
          @click="navigateTo('/goods-receipts')"
        />
      </div>
    </template>
  </main>
</template>
