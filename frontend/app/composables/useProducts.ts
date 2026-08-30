import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { ProductCreate, ProductPage, ProductPublic, ProductUpdate } from '~/types/api'

export interface ProductListParams {
  q?: string
  limit?: number
  offset?: number
}

const PRODUCTS_KEY = 'products'

/**
 * Product queries and mutations.
 *
 * Mutations invalidate the list rather than patching it in place: the server
 * owns `version`, ordering and the total, so re-reading is the only way the UI
 * ends up holding what the database actually contains.
 */
export function useProductList(params: Ref<ProductListParams>) {
  const api = createApiClient()

  return useQuery({
    // `params` is in the key, so changing the filter or page refetches and each
    // combination keeps its own cache entry.
    queryKey: [PRODUCTS_KEY, 'list', params],
    queryFn: () =>
      api<ProductPage>('/products', {
        query: {
          q: params.value.q || undefined,
          limit: params.value.limit ?? 20,
          offset: params.value.offset ?? 0,
        },
      }),
  })
}

export function useProduct(id: Ref<string | null>) {
  const api = createApiClient()

  return useQuery({
    queryKey: [PRODUCTS_KEY, 'one', id],
    queryFn: () => api<ProductPublic>(`/products/${id.value}`),
    enabled: computed(() => Boolean(id.value)),
  })
}

export function useCreateProduct() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ProductCreate) =>
      api<ProductPublic>('/products', { method: 'POST', body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [PRODUCTS_KEY] }),
  })
}

export function useUpdateProduct() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, payload }: { id: string, payload: ProductUpdate }) =>
      api<ProductPublic>(`/products/${id}`, { method: 'PATCH', body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [PRODUCTS_KEY] }),
  })
}
