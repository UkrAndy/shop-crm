import { expect, test } from '@playwright/test'

/**
 * Issue 24 — the whole Tracer Bullet, through the UI.
 *
 * This is the executable proof of the PRD's Definition of Done: log in, select
 * an organization, create a product, draft a goods receipt, post it, and see the
 * stock balance reflect the posted quantity. Every layer is real — browser, SSR,
 * API, domain, PostgreSQL — and nothing here talks to the API directly.
 */
const OWNER = { email: 'owner@example.com', password: 'seed-password-123' }

type Page = import('@playwright/test').Page

async function goto(page: Page, path: string) {
  await page.goto(path)
  await page.waitForSelector('html[data-hydrated="true"]')
}

function unique(prefix: string) {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

async function chooseOption(page: Page, testId: string, label: string) {
  await page.getByTestId(testId).click()
  // PrimeVue leaves closed overlays in the DOM; scope to the open one.
  await page.locator('[role="listbox"]:visible').last()
    .getByRole('option', { name: label, exact: true })
    .click()
}

test('log in, create a product, post a receipt, see the balance', async ({ page }) => {
  const productName = unique('Кава наскрізна')
  const supplierName = unique('ТОВ Наскрізний')

  // 1. Log in. The organization resolves itself — `owner` has exactly one.
  await goto(page, '/login')
  await page.getByTestId('login-email').fill(OWNER.email)
  await page.getByTestId('login-password').locator('input').fill(OWNER.password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL('/')
  await expect(page.getByTestId('active-organization')).toHaveText('ФОП Альфа')

  // 2. Create a product.
  await page.getByTestId('nav-products').click()
  await expect(page).toHaveURL('/products')
  await page.getByTestId('product-new').click()
  await page.getByTestId('product-name').fill(productName)
  await page.getByTestId('product-price').fill('25.00')
  await page.getByTestId('product-save').click()
  await expect(page.getByRole('cell', { name: productName })).toBeVisible()

  // 3. Draft a goods receipt for six of them.
  await goto(page, '/goods-receipts/new')
  await page.getByTestId('supplier-add-toggle').click()
  await page.getByTestId('supplier-new-name').fill(supplierName)
  await page.getByTestId('supplier-new-save').click()
  await expect(page.getByTestId('receipt-supplier')).toContainText(supplierName)

  await page.getByTestId('line-add').click()
  await chooseOption(page, 'line-product-0', productName)
  const quantity = page.getByTestId('line-quantity-0').locator('input')
  await quantity.fill('6')
  await quantity.blur()
  await page.getByTestId('line-price-0').fill('25.00')
  await expect(page.getByTestId('receipt-total')).toHaveText('150.00')

  await page.getByTestId('receipt-save').click()
  await expect(page).toHaveURL(/\/goods-receipts\/[0-9a-f-]{36}$/)

  // 4. Post it.
  await page.getByTestId('receipt-post').click()
  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')

  // 5. The balance reflects it — read from the movements the posting created,
  //    not from any stored counter.
  await goto(page, '/stock-balance')
  await chooseOption(page, 'balance-product', productName)

  const row = page.getByRole('row', { name: new RegExp(productName) })
  await expect(row).toContainText('6')

  // 6. And a second delivery aggregates rather than replaces.
  await goto(page, '/goods-receipts/new')
  await chooseOption(page, 'receipt-supplier', supplierName)
  await page.getByTestId('line-add').click()
  await chooseOption(page, 'line-product-0', productName)
  const secondQuantity = page.getByTestId('line-quantity-0').locator('input')
  await secondQuantity.fill('4')
  await secondQuantity.blur()
  await page.getByTestId('line-price-0').fill('25.00')
  await page.getByTestId('receipt-save').click()
  await expect(page).toHaveURL(/\/goods-receipts\/[0-9a-f-]{36}$/)
  await page.getByTestId('receipt-post').click()
  await expect(page.getByTestId('receipt-status')).toHaveText('Проведено')

  await goto(page, '/stock-balance')
  await chooseOption(page, 'balance-product', productName)
  await expect(page.getByRole('row', { name: new RegExp(productName) })).toContainText('10')
})

test('a product that never arrived shows a zero balance, not an error', async ({ page }) => {
  const productName = unique('Ніколи не надходив')

  await goto(page, '/login')
  await page.getByTestId('login-email').fill(OWNER.email)
  await page.getByTestId('login-password').locator('input').fill(OWNER.password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL('/')

  await goto(page, '/products')
  await page.getByTestId('product-new').click()
  await page.getByTestId('product-name').fill(productName)
  await page.getByTestId('product-price').fill('1.00')
  await page.getByTestId('product-save').click()
  await expect(page.getByRole('cell', { name: productName })).toBeVisible()

  await goto(page, '/stock-balance')
  await chooseOption(page, 'balance-product', productName)

  // Zero is an answer. An empty shelf and a typo must not look the same.
  await expect(page.getByRole('row', { name: new RegExp(productName) })).toContainText('0')
  await expect(page.getByTestId('balance-error')).toBeHidden()
})
