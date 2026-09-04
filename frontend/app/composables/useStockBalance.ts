import { useQuery } from '@tanstack/vue-query'

import type { StockBalancePage } from '~/types/api'

export interface StockBalanceParams {
  productId?: string | null
  limit?: number
  offset?: number
}

/**
 * Stock balance, aggregated server-side from movements.
 *
 * Nothing is cached beyond the query itself: the balance is derived, so the
 * only way to be sure it is current is to ask.
 */
export function useStockBalance(params: Ref<StockBalanceParams>) {
  const api = createApiClient()

  return useQuery({
    queryKey: ['stock-balance', params],
    queryFn: () =>
      api<StockBalancePage>('/stock-balance', {
        query: {
          product_id: params.value.productId || undefined,
          limit: params.value.limit ?? 50,
          offset: params.value.offset ?? 0,
        },
      }),
  })
}
