/**
 * Named aliases over the generated contract.
 *
 * `shared/api/schema.d.ts` is produced from the backend's OpenAPI document by
 * `pnpm api:generate` and is never edited by hand. This file exists only so the
 * app can say `ProductPublic` instead of
 * `components['schemas']['ProductPublic']` — it adds names, never fields. A
 * shape declared here that the API does not actually return would be exactly
 * the drift the generator was introduced to eliminate.
 */

import type { components } from '#shared/api/schema'

type Schemas = components['schemas']

export type UserPublic = Schemas['UserPublic']
export type SessionPublic = Schemas['SessionPublic']
export type OrganizationPublic = Schemas['OrganizationPublic']

export type ProductPublic = Schemas['ProductPublic']
export type ProductPage = Schemas['ProductPage']
export type ProductCreate = Schemas['ProductCreate']
export type ProductUpdate = Schemas['ProductUpdate']

export type CounterpartyPublic = Schemas['CounterpartyPublic']

export type GoodsReceiptSummary = Schemas['GoodsReceiptSummary']
export type GoodsReceiptPublic = Schemas['GoodsReceiptPublic']
export type GoodsReceiptPage = Schemas['GoodsReceiptPage']
export type GoodsReceiptCreate = Schemas['GoodsReceiptCreate']
export type GoodsReceiptUpdate = Schemas['GoodsReceiptUpdate']
export type GoodsReceiptLineInput = Schemas['GoodsReceiptLineInput']
export type GoodsReceiptLinePublic = Schemas['GoodsReceiptLinePublic']

export type StockBalanceRow = Schemas['StockBalanceRow']
export type StockBalancePage = Schemas['StockBalancePage']

/** The single envelope every 401/403/404/409/422 uses. */
export type ApiErrorResponse = Schemas['ErrorResponse']
export type ApiFieldError = Schemas['FieldError']
