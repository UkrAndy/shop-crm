import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  CounterpartyPublic,
  GoodsReceiptCreate,
  GoodsReceiptPage,
  GoodsReceiptPublic,
  GoodsReceiptUpdate,
} from '~/types/api'

const RECEIPTS_KEY = 'goods-receipts'
const COUNTERPARTIES_KEY = 'counterparties'

export function useGoodsReceiptList(params: Ref<{ limit?: number, offset?: number }>) {
  const api = createApiClient()

  return useQuery({
    queryKey: [RECEIPTS_KEY, 'list', params],
    queryFn: () =>
      api<GoodsReceiptPage>('/goods-receipts', {
        query: { limit: params.value.limit ?? 20, offset: params.value.offset ?? 0 },
      }),
  })
}

export function useGoodsReceipt(id: Ref<string | null>) {
  const api = createApiClient()

  return useQuery({
    queryKey: [RECEIPTS_KEY, 'one', id],
    queryFn: () => api<GoodsReceiptPublic>(`/goods-receipts/${id.value}`),
    enabled: computed(() => Boolean(id.value)),
  })
}

export function useCreateGoodsReceipt() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: GoodsReceiptCreate) =>
      api<GoodsReceiptPublic>('/goods-receipts', { method: 'POST', body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [RECEIPTS_KEY] }),
  })
}

export function useUpdateGoodsReceipt() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, payload }: { id: string, payload: GoodsReceiptUpdate }) =>
      api<GoodsReceiptPublic>(`/goods-receipts/${id}`, { method: 'PATCH', body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [RECEIPTS_KEY] }),
  })
}

export function useCounterparties() {
  const api = createApiClient()

  return useQuery({
    queryKey: [COUNTERPARTIES_KEY],
    queryFn: () => api<CounterpartyPublic[]>('/counterparties'),
  })
}

export function useCreateCounterparty() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (name: string) =>
      api<CounterpartyPublic>('/counterparties', { method: 'POST', body: { name } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [COUNTERPARTIES_KEY] }),
  })
}
