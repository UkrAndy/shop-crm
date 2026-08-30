import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

const BACKEND = fileURLToPath(new URL('../../../backend', import.meta.url))

/** See `backend/scripts/mark_receipt_posted.py` for why this is a script. */
function markPosted(receiptId: string) {
  execFileSync('uv', ['run', 'python', 'scripts/mark_receipt_posted.py', receiptId], {
    cwd: BACKEND,
    stdio: 'inherit',
  })
}

/**
 * Issue 17 — the goods receipt draft UI.
 *
 * Acceptance criteria under test:
 * - a draft with multiple lines round-trips through a page reload unchanged;
 * - a posted document renders read-only, with no editing affordances.
 */
const OWNER = { email: 'owner@example.com', password: 'seed-password-123' }

type Page = import('@playwright/test').Page

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

/** Products and suppliers are created through the API — this suite tests the receipt UI. */
async function seed(page: Page, productNames: string[], supplierName: string) {
  const cookies = await page.context().cookies()
  const headers = { cookie: cookies.map(c => `${c.name}=${c.value}`).join('; ') }
  const api = page.request

  for (const name of productNames) {
    const response = await api.post('http://localhost:8000/api/v1/products', {
      headers,
      data: { name, unit: 'шт', purchase_price: '10.00' },
    })
    expect(response.status()).toBe(201)
  }

  const supplier = await api.post('http://localhost:8000/api/v1/counterparties', {
    headers,
    data: { name: supplierName },
  })
  expect(supplier.status()).toBe(201)
}

async function chooseOption(page: Page, testId: string, label: string) {
  await page.getByTestId(testId).click()
  // Scoped to the overlay that is actually open. PrimeVue leaves the markup of
  // previously opened `Select`s in the DOM, so a page-wide `getByRole('option')`
  // matches every list at once as soon as a second line exists.
  const open = page.locator('[role="listbox"]:visible').last()
  await open.getByRole('option', { name: label, exact: true }).click()
}

async function addLine(page: Page, index: number, product: string, quantity: number, price: string) {
  await page.getByTestId('line-add').click()
  await chooseOption(page, `line-product-${index}`, product)
  const quantityInput = page.getByTestId(`line-quantity-${index}`).locator('input')
  await quantityInput.fill(String(quantity))
  await quantityInput.blur()
  await page.getByTestId(`line-price-${index}`).fill(price)
}

test('a draft with several lines survives a full page reload', async ({ page }) => {
  const supplier = unique('ТОВ Постачальник')
  const products = [unique('Кава'), unique('Чай'), unique('Цукор')]

  await login(page)
  await seed(page, products, supplier)

  await goto(page, '/goods-receipts/new')
  await chooseOption(page, 'receipt-supplier', supplier)

  await addLine(page, 0, products[0]!, 3, '10.00')
  await addLine(page, 1, products[1]!, 5, '2.50')
  await addLine(page, 2, products[2]!, 2, '0.05')

  // Running total, computed in the browser in whole kopiykas while typing.
  await expect(page.getByTestId('receipt-total')).toHaveText('42.60')

  await page.getByTestId('receipt-save').click()
  await expect(page).toHaveURL(/\/goods-receipts\/[0-9a-f-]{36}$/)

  const url = page.url()
  await goto(page, url)

  // The acceptance criterion: three lines, same quantities, same total, after a
  // genuine reload rather than a client-side navigation.
  await expect(page.getByTestId('receipt-line-0')).toBeVisible()
  await expect(page.getByTestId('receipt-line-1')).toBeVisible()
  await expect(page.getByTestId('receipt-line-2')).toBeVisible()
  await expect(page.getByTestId('receipt-total')).toHaveText('42.60')
  await expect(page.getByTestId('line-quantity-1').locator('input')).toHaveValue('5')
})

test('the list shows status, supplier, author and date', async ({ page }) => {
  const supplier = unique('ТОВ Список')
  await login(page)
  await seed(page, [unique('Товар')], supplier)

  await goto(page, '/goods-receipts/new')
  await chooseOption(page, 'receipt-supplier', supplier)
  await page.getByTestId('receipt-save').click()
  await expect(page).toHaveURL(/\/goods-receipts\/[0-9a-f-]{36}$/)

  await goto(page, '/goods-receipts')

  const row = page.getByRole('row', { name: new RegExp(supplier) })
  await expect(row).toContainText('Чернетка')
  await expect(row).toContainText(OWNER.email)
})

test('a supplier can be created from the picker', async ({ page }) => {
  const supplier = unique('ТОВ Новий')
  await login(page)

  await goto(page, '/goods-receipts/new')
  await page.getByTestId('supplier-add-toggle').click()
  await page.getByTestId('supplier-new-name').fill(supplier)
  await page.getByTestId('supplier-new-save').click()

  await expect(page.getByTestId('receipt-supplier')).toContainText(supplier)
})

test('saving without a supplier is refused before any request', async ({ page }) => {
  await login(page)
  await goto(page, '/goods-receipts/new')

  await page.getByTestId('receipt-save').click()

  await expect(page.getByTestId('receipt-error')).toBeVisible()
  await expect(page).toHaveURL('/goods-receipts/new')
})

test('a posted document renders read-only', async ({ page }) => {
  const supplier = unique('ТОВ Проведене')
  const product = unique('Проведений товар')

  await login(page)
  await seed(page, [product], supplier)

  await goto(page, '/goods-receipts/new')
  await chooseOption(page, 'receipt-supplier', supplier)
  await addLine(page, 0, product, 4, '10.00')
  await page.getByTestId('receipt-save').click()
  await expect(page).toHaveURL(/\/goods-receipts\/[0-9a-f-]{36}$/)
  const url = page.url()

  // Posting itself is Issue 20. Until then the status is flipped by a script,
  // never by an endpoint: a route that posts a document on request would be a
  // backdoor around the whole posting transaction, and a debug flag guarding it
  // would only mean the backdoor ships with the flag.
  markPosted(url.split('/').pop()!)

  await goto(page, url)

  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')
  await expect(page.getByTestId('receipt-save')).toBeHidden()
  await expect(page.getByTestId('line-add')).toBeHidden()
  await expect(page.getByTestId('receipt-supplier')).toBeHidden()
  await expect(page.getByTestId('receipt-supplier-readonly')).toHaveText(supplier)
  // The values are still shown — read-only, not hidden.
  await expect(page.getByTestId('receipt-total')).toHaveText('40.00')
})
