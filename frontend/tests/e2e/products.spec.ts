import { expect, test } from '@playwright/test'

/**
 * Issue 13 — the products UI end to end.
 *
 * The conflict case is the one that matters: a 409 must produce an explicit
 * "this changed, reload and retry" prompt, never a silent overwrite and never a
 * generic error toast.
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

/** Product names are unique per run so a shared database cannot make tests collide. */
function uniqueName(prefix: string) {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

async function createProduct(page: Page, name: string, price = '12.50', barcode = '') {
  await page.getByTestId('product-new').click()
  await expect(page.getByTestId('product-dialog')).toBeVisible()
  await page.getByTestId('product-name').fill(name)
  await page.getByTestId('product-price').fill(price)
  if (barcode) await page.getByTestId('product-barcode').fill(barcode)
  await page.getByTestId('product-save').click()
  await expect(page.getByTestId('product-dialog')).toBeHidden()
}

test('creating a product shows it in the list without a manual refresh', async ({ page }) => {
  await login(page)
  await goto(page, '/products')

  const name = uniqueName('Кава')
  await createProduct(page, name)

  // No reload: the mutation invalidates the list query and it refetches.
  await expect(page.getByRole('cell', { name })).toBeVisible()
})

test('the search filter narrows the list', async ({ page }) => {
  await login(page)
  await goto(page, '/products')

  const wanted = uniqueName('Чай')
  const other = uniqueName('Печиво')
  await createProduct(page, wanted)
  await createProduct(page, other)

  await page.getByTestId('products-search').fill(wanted)

  await expect(page.getByRole('cell', { name: wanted })).toBeVisible()
  await expect(page.getByRole('cell', { name: other })).toBeHidden()
})

test('client-side validation refuses a sub-kopiyka price before any request', async ({ page }) => {
  await login(page)
  await goto(page, '/products')

  await page.getByTestId('product-new').click()
  await page.getByTestId('product-name').fill(uniqueName('Округлення'))
  await page.getByTestId('product-price').fill('10.005')
  await page.getByTestId('product-save').click()

  await expect(page.getByTestId('product-price-error')).toBeVisible()
  await expect(page.getByTestId('product-dialog')).toBeVisible()
})

test('a duplicate barcode is reported on the barcode field', async ({ page }) => {
  await login(page)
  await goto(page, '/products')

  const barcode = `482${Date.now()}`.slice(0, 13)
  await createProduct(page, uniqueName('Перший'), '1.00', barcode)

  await page.getByTestId('product-new').click()
  await page.getByTestId('product-name').fill(uniqueName('Другий'))
  await page.getByTestId('product-price').fill('1.00')
  await page.getByTestId('product-barcode').fill(barcode)
  await page.getByTestId('product-save').click()

  await expect(page.getByTestId('product-barcode-error')).toBeVisible()
})

test('a stale edit offers reload-and-retry instead of overwriting', async ({ page, request }) => {
  await login(page)
  await goto(page, '/products')

  const name = uniqueName('Конфлікт')
  await createProduct(page, name)
  await expect(page.getByRole('cell', { name })).toBeVisible()

  // Open the editor, so the form now holds version 1.
  await page.getByRole('cell', { name }).click()
  const row = page.getByRole('row', { name: new RegExp(name) })
  await row.getByRole('button', { name: 'Змінити' }).click()
  await expect(page.getByTestId('product-dialog')).toBeVisible()

  // Meanwhile somebody else saves version 2, straight through the API using
  // the browser's own session cookie.
  const cookies = await page.context().cookies()
  const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ')
  const list = await request.get('http://localhost:8000/api/v1/products', {
    headers: { cookie: cookieHeader },
    params: { q: name },
  })
  const product = (await list.json()).items[0]
  const patched = await request.patch(`http://localhost:8000/api/v1/products/${product.id}`, {
    headers: { cookie: cookieHeader },
    data: { version: product.version, name: `${name} (чуже)` },
  })
  expect(patched.status()).toBe(200)

  await page.getByTestId('product-name').fill(`${name} (моє)`)
  await page.getByTestId('product-save').click()

  // The explicit conflict experience the backlog asks for — not a generic toast.
  await expect(page.getByTestId('product-conflict')).toBeVisible()
  await expect(page.getByTestId('product-conflict-reload')).toBeVisible()

  await page.getByTestId('product-conflict-reload').click()

  // The other writer's change survived; ours was not silently applied.
  await expect(page.getByRole('cell', { name: `${name} (чуже)` })).toBeVisible()
})
