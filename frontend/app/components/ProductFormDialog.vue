<script setup lang="ts">
import { z } from 'zod'

import type { ProductPublic } from '~/types/api'

const props = defineProps<{
  /** `null` creates; a product edits it. */
  product: ProductPublic | null
}>()

const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ saved: [] }>()

const createProduct = useCreateProduct()
const updateProduct = useUpdateProduct()

// Mirrors the server's rules so the user hears about a mistake immediately. It
// does not replace them: the API validates the same body and answers 422 in the
// shared envelope no matter what the client checked.
const schema = z.object({
  name: z.string().trim().min(1, "Вкажіть назву").max(255, 'Не більше 255 символів'),
  unit: z.string().trim().min(1, 'Вкажіть одиницю').max(32, 'Не більше 32 символів'),
  // Two decimals, matching numeric(14,2). Without this the server would answer
  // 422 anyway — but the user would learn it a round-trip later.
  purchase_price: z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, 'Ціна — невід’ємне число з не більш ніж двома знаками'),
  barcode: z.string().trim().max(64, 'Не більше 64 символів'),
})

const form = reactive({ name: '', unit: 'шт', purchase_price: '', barcode: '' })
const fieldErrors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const conflict = ref(false)

const isEdit = computed(() => props.product !== null)
const saving = computed(() => createProduct.isPending.value || updateProduct.isPending.value)

watch(
  () => [visible.value, props.product] as const,
  ([open, product]) => {
    if (!open) return
    fieldErrors.value = {}
    formError.value = null
    conflict.value = false
    form.name = product?.name ?? ''
    form.unit = product?.unit ?? 'шт'
    form.purchase_price = product?.purchase_price ?? ''
    form.barcode = product?.barcode ?? ''
  },
  { immediate: true },
)

function applyServerFieldErrors(error: unknown) {
  const body = (error as { data?: import('~/types/api').ApiErrorResponse })?.data
  for (const item of body?.error?.fields ?? []) {
    // Server paths look like "body.purchase_price"; the last segment is the field.
    const field = item.field.split('.').pop() ?? ''
    if (field && !fieldErrors.value[field]) fieldErrors.value[field] = item.message
  }
}

async function onSubmit() {
  fieldErrors.value = {}
  formError.value = null
  conflict.value = false

  const parsed = schema.safeParse({ ...form })
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      const field = String(issue.path[0] ?? '')
      if (field && !fieldErrors.value[field]) fieldErrors.value[field] = issue.message
    }
    return
  }

  const body = {
    name: parsed.data.name,
    unit: parsed.data.unit,
    purchase_price: parsed.data.purchase_price,
    barcode: parsed.data.barcode || null,
  }

  try {
    if (props.product) {
      await updateProduct.mutateAsync({
        id: props.product.id,
        payload: { ...body, version: props.product.version },
      })
    }
    else {
      await createProduct.mutateAsync(body)
    }
    visible.value = false
    emit('saved')
  }
  catch (error) {
    const code = apiErrorCode(error)
    if (code === 'version_conflict') {
      // Never overwrite silently. The user is told the record moved and is
      // offered a reload; their typed values stay on screen until they choose.
      conflict.value = true
      return
    }
    if (code === 'barcode_taken') {
      fieldErrors.value.barcode = apiErrorMessage(error, 'Цей штрихкод уже використовується.')
      return
    }
    applyServerFieldErrors(error)
    formError.value = apiErrorMessage(error, 'Не вдалося зберегти товар.')
  }
}

function reloadAndRetry() {
  // Reload-and-retry, the pattern the backlog asks for: discard nothing on the
  // server, re-read it, and let the user decide what to do with the fresh values.
  conflict.value = false
  visible.value = false
  emit('saved')
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    :header="isEdit ? 'Редагувати товар' : 'Новий товар'"
    modal
    :style="{ width: '32rem' }"
    data-testid="product-dialog"
  >
    <Message
      v-if="conflict"
      data-testid="product-conflict"
      severity="warn"
      :closable="false"
      class="mb-4"
    >
      <p class="mb-2">
        Товар змінив хтось інший, поки ви редагували. Ваші зміни не збережено, щоб
        не перезаписати чужі.
      </p>
      <Button
        data-testid="product-conflict-reload"
        label="Перезавантажити та повторити"
        size="small"
        @click="reloadAndRetry"
      />
    </Message>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <div class="flex flex-col gap-1">
        <label for="product-name" class="text-sm font-medium">Назва</label>
        <InputText
          id="product-name"
          v-model="form.name"
          data-testid="product-name"
          :invalid="Boolean(fieldErrors.name)"
        />
        <small v-if="fieldErrors.name" data-testid="product-name-error" class="text-red-600">
          {{ fieldErrors.name }}
        </small>
      </div>

      <div class="flex flex-col gap-1">
        <label for="product-unit" class="text-sm font-medium">Одиниця</label>
        <InputText
          id="product-unit"
          v-model="form.unit"
          data-testid="product-unit"
          :invalid="Boolean(fieldErrors.unit)"
        />
        <small v-if="fieldErrors.unit" class="text-red-600">{{ fieldErrors.unit }}</small>
      </div>

      <div class="flex flex-col gap-1">
        <label for="product-price" class="text-sm font-medium">Закупівельна ціна</label>
        <InputText
          id="product-price"
          v-model="form.purchase_price"
          data-testid="product-price"
          inputmode="decimal"
          :invalid="Boolean(fieldErrors.purchase_price)"
        />
        <small v-if="fieldErrors.purchase_price" data-testid="product-price-error" class="text-red-600">
          {{ fieldErrors.purchase_price }}
        </small>
      </div>

      <div class="flex flex-col gap-1">
        <label for="product-barcode" class="text-sm font-medium">Штрихкод (необов’язково)</label>
        <InputText
          id="product-barcode"
          v-model="form.barcode"
          data-testid="product-barcode"
          :invalid="Boolean(fieldErrors.barcode)"
        />
        <small v-if="fieldErrors.barcode" data-testid="product-barcode-error" class="text-red-600">
          {{ fieldErrors.barcode }}
        </small>
      </div>

      <Message v-if="formError" data-testid="product-error" severity="error" :closable="false">
        {{ formError }}
      </Message>

      <div class="flex justify-end gap-2">
        <Button
          type="button"
          label="Скасувати"
          severity="secondary"
          @click="visible = false"
        />
        <Button
          type="submit"
          data-testid="product-save"
          label="Зберегти"
          :loading="saving"
          :disabled="conflict"
        />
      </div>
    </form>
  </Dialog>
</template>
