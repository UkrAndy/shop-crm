import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

/**
 * Issue 21 — posting from the UI.
 *
 * Acceptance criteria under test:
 * - double-clicking the post button produces one movement, verified in the database;
 * - after posting, the document renders read-only.
 */
const OWNER = { email: 'owner@example.com', password: 'seed-password-123' }
const BACKEND = fileURLToPath(new URL('../../../backend', import.meta.url))

type Page = import('@playwright/test').Page

/** See `backend/scripts/count_movements.py` for why this is a script. */
function countMovements(receiptId: string) {
  const output = execFileSync(
    'uv',
    ['run', 'python', 'scripts/count_movements.py', receiptId],
    { cwd: BACKEND, encoding: 'utf8' },
  )
  const batches = Number(/batches=(\d+)/.exec(output)?.[1])
  const movements = Number(/movements=(\d+)/.exec(output)?.[1])
  return { batches, movements }
}

async function goto(page: Page, path: string) {
  await page.goto(path)
  await page.waitForSelector('html[data-hydrated="true"]')
}

async function login(page: Page) {
  await goto(page, '/login')
  await page.getByTestId('login-email').fill(OWNER.email)
  await page.getByTestId('login-password').locator('input').fill(OWNER.password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL('/')
}

function unique(prefix: string) {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

/** Build a draft through the API — this suite is about the posting UI. */
async function seedDraft(page: Page, lines: number) {
  const cookies = await page.context().cookies()
  const headers = { cookie: cookies.map(c => `${c.name}=${c.value}`).join('; ') }
  const api = page.request
  const base = 'http://localhost:8000/api/v1'

  const supplier = await api.post(`${base}/counterparties`, {
    headers,
    data: { name: unique('ТОВ Проведення') },
  })
  expect(supplier.status()).toBe(201)

  const payloadLines = []
  for (let index = 0; index < lines; index += 1) {
    const product = await api.post(`${base}/products`, {
      headers,
      data: { name: unique('Товар'), unit: 'шт', purchase_price: '10.00' },
    })
    expect(product.status()).toBe(201)
    payloadLines.push({
      product_id: (await product.json()).id,
      quantity: 3,
      purchase_price: '10.00',
    })
  }

  const receipt = await api.post(`${base}/goods-receipts`, {
    headers,
    data: { counterparty_id: (await supplier.json()).id, lines: payloadLines },
  })
  expect(receipt.status()).toBe(201)
  return await receipt.json()
}

test('posting flips the document to read-only', async ({ page }) => {
  await login(page)
  const receipt = await seedDraft(page, 1)

  await goto(page, `/goods-receipts/${receipt.id}`)
  await page.getByTestId('receipt-post').click()

  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')
  await expect(page.getByTestId('receipt-post')).toBeHidden()
  await expect(page.getByTestId('receipt-save')).toBeHidden()
  await expect(page.getByTestId('line-add')).toBeHidden()
  await expect(page.getByTestId('receipt-supplier')).toBeHidden()
})

test('double-clicking post produces exactly one movement', async ({ page }) => {
  await login(page)
  const receipt = await seedDraft(page, 1)

  await goto(page, `/goods-receipts/${receipt.id}`)

  // Two clicks as fast as Playwright can manage them. The button disables while
  // the request is in flight, and the row lock plus the idempotency key cover
  // whatever slips through.
  const button = page.getByTestId('receipt-post')
  await button.dblclick()

  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')

  // The claim is about the database, not about the screen.
  expect(countMovements(receipt.id)).toEqual({ batches: 1, movements: 1 })
})

test('one batch and one movement per line', async ({ page }) => {
  await login(page)
  const receipt = await seedDraft(page, 3)

  await goto(page, `/goods-receipts/${receipt.id}`)
  await page.getByTestId('receipt-post').click()
  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')

  expect(countMovements(receipt.id)).toEqual({ batches: 3, movements: 3 })
})

test('an empty document cannot be posted', async ({ page }) => {
  await login(page)
  const receipt = await seedDraft(page, 0)

  await goto(page, `/goods-receipts/${receipt.id}`)

  // Disabled rather than clickable-then-rejected: the server answers 422, but a
  // control that cannot work should not invite the click.
  await expect(page.getByTestId('receipt-post')).toBeDisabled()
})
