<script setup lang="ts">
const productId = ref<string | null>(null)
const page = ref(0)
const rows = ref(20)

// The picker needs the catalog; the table needs the balances.
const productParams = ref({ limit: 200, offset: 0 })
const { data: products } = useProductList(productParams)

const params = computed(() => ({
  productId: productId.value,
  limit: rows.value,
  offset: page.value * rows.value,
}))
const { data, isPending, isError, error } = useStockBalance(params)

watch(productId, () => {
  page.value = 0
})

function onPage(event: { page: number, rows: number }) {
  page.value = event.page
  rows.value = event.rows
}

const dateFormatter = new Intl.DateTimeFormat('uk-UA', {
  dateStyle: 'short',
  timeStyle: 'short',
})

function formatDate(value: string | null) {
  return value ? dateFormatter.format(new Date(value)) : '—'
}
</script>

<template>
  <main class="mx-auto flex max-w-4xl flex-col gap-4 p-8">
    <h1 data-testid="balance-title" class="text-2xl font-semibold">
      Залишки
    </h1>

    <p class="text-sm text-gray-600">
      Порахований із рухів товару, а не з окремої колонки: кожне проведене
      надходження — це рух, і сума рухів і є залишок.
    </p>

    <div class="flex items-center gap-2">
      <Select
        v-model="productId"
        data-testid="balance-product"
        :options="products?.items ?? []"
        option-label="name"
        option-value="id"
        filter
        show-clear
        placeholder="Усі товари"
        class="w-full max-w-sm"
      />
    </div>

    <Message v-if="isError" data-testid="balance-error" severity="error" :closable="false">
      {{ apiErrorMessage(error, 'Не вдалося завантажити залишки.') }}
    </Message>

    <DataTable
      :value="data?.items ?? []"
      data-testid="balance-table"
      :loading="isPending"
      :rows="rows"
      :total-records="data?.total ?? 0"
      :first="page * rows"
      lazy
      paginator
      :rows-per-page-options="[10, 20, 50]"
      data-key="product_id"
      @page="onPage"
    >
      <template #empty>
        <span data-testid="balance-empty">Рухів товару ще не було.</span>
      </template>

      <Column field="product_name" header="Товар" />
      <Column header="Склад">
        <template #body="{ data: row }">
          {{ row.warehouse_id ? 'Основний склад' : '—' }}
        </template>
      </Column>
      <Column header="Кількість" class="text-right">
        <template #body="{ data: row }">
          <span
            :data-testid="`balance-quantity-${row.product_id}`"
            class="tabular-nums font-medium"
          >{{ row.quantity_balance }}</span>
        </template>
      </Column>
      <Column header="Останній рух">
        <template #body="{ data: row }">
          {{ formatDate(row.last_movement_at) }}
        </template>
      </Column>
    </DataTable>
  </main>
</template>
