<script setup lang="ts">
import type { GoodsReceiptSummary } from '~/types/api'

const page = ref(0)
const rows = ref(20)

const params = computed(() => ({ limit: rows.value, offset: page.value * rows.value }))
const { data, isPending, isError, error } = useGoodsReceiptList(params)

function onPage(event: { page: number, rows: number }) {
  page.value = event.page
  rows.value = event.rows
}

function open(receipt: GoodsReceiptSummary) {
  return navigateTo(`/goods-receipts/${receipt.id}`)
}

const dateFormatter = new Intl.DateTimeFormat('uk-UA', {
  dateStyle: 'short',
  timeStyle: 'short',
})

function formatDate(value: string) {
  return dateFormatter.format(new Date(value))
}
</script>

<template>
  <main class="mx-auto flex max-w-5xl flex-col gap-4 p-8">
    <div class="flex items-center justify-between gap-4">
      <h1 data-testid="receipts-title" class="text-2xl font-semibold">
        Надходження
      </h1>
      <Button
        data-testid="receipt-new"
        label="Нове надходження"
        @click="navigateTo('/goods-receipts/new')"
      />
    </div>

    <Message v-if="isError" data-testid="receipts-error" severity="error" :closable="false">
      {{ apiErrorMessage(error, 'Не вдалося завантажити надходження.') }}
    </Message>

    <DataTable
      :value="data?.items ?? []"
      data-testid="receipts-table"
      :loading="isPending"
      :rows="rows"
      :total-records="data?.total ?? 0"
      :first="page * rows"
      lazy
      paginator
      :rows-per-page-options="[10, 20, 50]"
      data-key="id"
      @page="onPage"
    >
      <template #empty>
        <span data-testid="receipts-empty">Надходжень ще немає.</span>
      </template>

      <Column header="Статус">
        <template #body="{ data: row }">
          <Tag
            :data-testid="`receipt-status-${row.id}`"
            :value="row.status === 'posted' ? 'Проведено' : 'Чернетка'"
            :severity="row.status === 'posted' ? 'success' : 'secondary'"
          />
        </template>
      </Column>
      <Column field="counterparty_name" header="Постачальник" />
      <Column field="created_by_email" header="Створив" />
      <Column header="Створено">
        <template #body="{ data: row }">
          {{ formatDate(row.created_at) }}
        </template>
      </Column>
      <Column header="Сума" class="text-right">
        <template #body="{ data: row }">
          <span class="tabular-nums">{{ row.total }}</span>
        </template>
      </Column>
      <Column header="" style="width: 6rem">
        <template #body="{ data: row }">
          <Button
            :data-testid="`receipt-open-${row.id}`"
            label="Відкрити"
            size="small"
            severity="secondary"
            text
            @click="open(row)"
          />
        </template>
      </Column>
    </DataTable>
  </main>
</template>
