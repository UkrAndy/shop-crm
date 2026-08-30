<script setup lang="ts">
import type { GoodsReceiptLineInput, ProductPublic } from '~/types/api'

/** A line while it is being edited: quantity and price are still text. */
export interface DraftLine {
  product_id: string | null
  quantity: number
  purchase_price: string
}

const props = defineProps<{ readonly?: boolean }>()
const lines = defineModel<DraftLine[]>({ required: true })

// The whole catalog, filtered in the picker. Adequate for the tracer bullet's
// scale; a catalog large enough to outgrow one page needs a server-side search
// in the picker, which is a change to make when there is one, not before.
const productParams = ref({ limit: 200, offset: 0 })
const { data: products } = useProductList(productParams)

const options = computed(() => products.value?.items ?? [])

function productById(id: string | null): ProductPublic | undefined {
  return options.value.find(item => item.id === id)
}

function addLine() {
  lines.value = [...lines.value, { product_id: null, quantity: 1, purchase_price: '' }]
}

function removeLine(index: number) {
  lines.value = lines.value.filter((_, position) => position !== index)
}

/** Prefill the price from the catalog — it is the usual answer, still editable. */
function onProductChosen(index: number, productId: string) {
  const product = productById(productId)
  const current = lines.value[index]
  if (!product || !current) return
  if (!current.purchase_price) {
    lines.value = lines.value.map((item, position) =>
      position === index ? { ...item, purchase_price: product.purchase_price } : item,
    )
  }
}

function lineTotal(item: DraftLine): string {
  const kopiyky = lineTotalKopiyky(item.purchase_price, item.quantity)
  return kopiyky === null ? '—' : formatKopiyky(kopiyky)
}

/**
 * Running total in whole kopiykas.
 *
 * Computed in integers rather than with floating point, so the figure the user
 * watches while typing is the one the server will confirm on save.
 */
const total = computed(() => {
  let kopiyky = 0
  for (const item of lines.value) {
    const value = lineTotalKopiyky(item.purchase_price, item.quantity)
    if (value === null) return null
    kopiyky += value
  }
  return formatKopiyky(kopiyky)
})

/** The payload shape, for the parent to send. Invalid lines are the parent's problem. */
function toPayload(): GoodsReceiptLineInput[] {
  return lines.value
    .filter((item): item is DraftLine & { product_id: string } => Boolean(item.product_id))
    .map(item => ({
      product_id: item.product_id,
      quantity: item.quantity,
      purchase_price: item.purchase_price,
    }))
}

defineExpose({ toPayload })
</script>

<template>
  <div class="flex flex-col gap-3">
    <table class="w-full text-sm" data-testid="receipt-lines">
      <thead>
        <tr class="border-b text-left">
          <th class="py-2">
            Товар
          </th>
          <th class="w-24 py-2">
            Кількість
          </th>
          <th class="w-32 py-2">
            Ціна
          </th>
          <th class="w-28 py-2 text-right">
            Сума
          </th>
          <th v-if="!props.readonly" class="w-12" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in lines" :key="index" :data-testid="`receipt-line-${index}`">
          <td class="py-1 pr-2">
            <Select
              v-if="!props.readonly"
              :model-value="item.product_id"
              :data-testid="`line-product-${index}`"
              :options="options"
              option-label="name"
              option-value="id"
              filter
              placeholder="Оберіть товар"
              class="w-full"
              @update:model-value="(value: string) => {
                lines[index]!.product_id = value
                onProductChosen(index, value)
              }"
            />
            <span v-else>{{ productById(item.product_id)?.name ?? '—' }}</span>
          </td>
          <td class="py-1 pr-2">
            <InputNumber
              v-if="!props.readonly"
              v-model="item.quantity"
              :data-testid="`line-quantity-${index}`"
              :min="1"
              :max-fraction-digits="0"
              show-buttons
              fluid
            />
            <span v-else>{{ item.quantity }}</span>
          </td>
          <td class="py-1 pr-2">
            <InputText
              v-if="!props.readonly"
              v-model="item.purchase_price"
              :data-testid="`line-price-${index}`"
              inputmode="decimal"
              fluid
            />
            <span v-else class="tabular-nums">{{ item.purchase_price }}</span>
          </td>
          <td class="py-1 text-right tabular-nums" :data-testid="`line-total-${index}`">
            {{ lineTotal(item) }}
          </td>
          <td v-if="!props.readonly" class="py-1 text-right">
            <Button
              :data-testid="`line-remove-${index}`"
              icon="pi pi-times"
              label="✕"
              severity="danger"
              text
              size="small"
              @click="removeLine(index)"
            />
          </td>
        </tr>
        <tr v-if="lines.length === 0">
          <td colspan="5" class="py-3 text-gray-500" data-testid="receipt-lines-empty">
            Рядків ще немає.
          </td>
        </tr>
      </tbody>
    </table>

    <div class="flex items-center justify-between">
      <Button
        v-if="!props.readonly"
        data-testid="line-add"
        label="Додати рядок"
        severity="secondary"
        size="small"
        @click="addLine"
      />
      <span v-else />

      <span class="text-sm">
        Разом:
        <strong data-testid="receipt-total" class="tabular-nums">{{ total ?? '—' }}</strong>
      </span>
    </div>
  </div>
</template>
