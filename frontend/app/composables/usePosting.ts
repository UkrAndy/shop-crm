import { useMutation, useQueryClient } from '@tanstack/vue-query'

import type { GoodsReceiptPublic } from '~/types/api'

/**
 * Post a goods receipt.
 *
 * The `Idempotency-Key` is supplied by the caller rather than generated here,
 * because it must stay **the same across retries of one attempt**. A key
 * generated per request would make every retry a new command, which is the same
 * as having no idempotency at all — the server would refuse the second one on
 * status, but a network failure the client never saw the answer to would become
 * unretryable.
 */
export function usePostReceipt() {
  const api = createApiClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, version, idempotencyKey }: {
      id: string
      version: number
      idempotencyKey: string
    }) =>
      api<GoodsReceiptPublic>(`/goods-receipts/${id}/post`, {
        method: 'POST',
        body: { version },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goods-receipts'] }),
  })
}

/**
 * A key that identifies one posting *attempt*, not one request.
 *
 * Rooted in the document and the version being posted, so a retry after a
 * timeout replays instead of re-executing, while a genuinely new attempt on a
 * changed document gets a new key.
 */
export function postingKey(receiptId: string, version: number): string {
  return `post:${receiptId}:${version}:${attemptNonce(receiptId, version)}`
}

const nonces = new Map<string, string>()

function attemptNonce(receiptId: string, version: number): string {
  const slot = `${receiptId}:${version}`
  let nonce = nonces.get(slot)
  if (!nonce) {
    // `randomUUID` needs a secure context; the fallback keeps the dev server and
    // any plain-HTTP deployment working rather than throwing at the worst moment.
    nonce = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
    nonces.set(slot, nonce)
  }
  return nonce
}
