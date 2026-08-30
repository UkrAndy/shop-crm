<script setup lang="ts">
import type { ProductPublic } from '~/types/api'

const search = ref('')
const page = ref(0)
const rows = ref(20)

// Debounced by hand rather than by pulling in VueUse for one helper. Typing
// must not fire a request per keystroke, and the page resets to the first
// whenever the filter changes — otherwise a narrower search lands the user on a
// page that no longer exists.
const debouncedSearch = ref('')
let searchTimer: ReturnType<typeof setTimeout> | undefined

watch(search, (value) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value
    page.value = 0
  }, 250)
})

onBeforeUnmount(() => clearTimeout(searchTimer))

const params = computed(() => ({
  q: debouncedSearch.value,
  limit: rows.value,
  offset: page.value * rows.value,
}))

const { data, isPending, isError, error, refetch } = useProductList(params)

const dialogVisible = ref(false)
const editing = ref<ProductPublic | null>(null)

function openCreate() {
  editing.value = null
  dialogVisible.value = true
}

function openEdit(product: ProductPublic) {
  editing.value = product
  dialogVisible.value = true
}

function onPage(event: { page: number, rows: number }) {
  page.value = event.page
  rows.value = event.rows
}
</script>

<template>
  <main class="mx-auto flex max-w-4xl flex-col gap-4 p-8">
    <div class="flex items-center justify-between gap-4">
      <h1 data-testid="products-title" class="text-2xl font-semibold">
        Товари
      </h1>
      <Button data-testid="product-new" label="Новий товар" @click="openCreate" />
    </div>

    <InputText
      v-model="search"
      data-testid="products-search"
      placeholder="Пошук за назвою або штрихкодом"
      class="w-full"
    />

    <Message v-if="isError" data-testid="products-error" severity="error" :closable="false">
      {{ apiErrorMessage(error, 'Не вдалося завантажити товари.') }}
    </Message>

    <DataTable
      :value="data?.items ?? []"
      data-testid="products-table"
      :loading="isPending"
      :rows="rows"
      :total-records="data?.total ?? 0"
      :first="page * rows"
      lazy
      paginator
      :rows-per-page-options="[10, 20, 50]"
      sort-mode="single"
      data-key="id"
      @page="onPage"
    >
      <template #empty>
        <span data-testid="products-empty">Товарів ще немає.</span>
      </template>

      <Column field="name" header="Назва" sortable />
      <Column field="barcode" header="Штрихкод">
        <template #body="{ data: row }">
          {{ row.barcode ?? '—' }}
        </template>
      </Column>
      <Column field="unit" header="Од." />
      <Column field="purchase_price" header="Ціна закупівлі" sortable>
        <template #body="{ data: row }">
          <span class="tabular-nums">{{ row.purchase_price }}</span>
        </template>
      </Column>
      <Column header="" style="width: 6rem">
        <template #body="{ data: row }">
          <Button
            :data-testid="`product-edit-${row.id}`"
            label="Змінити"
            size="small"
            severity="secondary"
            text
            @click="openEdit(row)"
          />
        </template>
      </Column>
    </DataTable>

    <ProductFormDialog
      v-model:visible="dialogVisible"
      :product="editing"
      @saved="refetch()"
    />
  </main>
</template>
