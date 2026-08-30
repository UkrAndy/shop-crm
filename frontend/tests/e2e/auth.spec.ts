import { expect, test } from '@playwright/test'

/**
 * Issue 9 — authentication end to end.
 *
 * These accounts come from `backend/scripts/seed_dev.py`, applied by
 * `global-setup.ts`. `owner` belongs to one organization, `multi` to two, which
 * is what makes "the server does not guess" observable in the UI.
 */
const OWNER = { email: 'owner@example.com', password: 'seed-password-123' }
const MULTI = { email: 'multi@example.com', password: 'seed-password-123' }

const ALPHA = 'ФОП Альфа'
const BETA = 'ФОП Бета'

type Page = import('@playwright/test').Page

/**
 * Navigate and wait until Vue has hydrated.
 *
 * Without the wait, `fill()` writes into server-rendered markup that Vue then
 * re-renders from its own empty state, and the form submits blank.
 */
async function goto(page: Page, path: string) {
  await page.goto(path)
  await page.waitForSelector('html[data-hydrated="true"]')
}

async function login(page: Page, user: typeof OWNER) {
  await goto(page, '/login')
  await page.getByTestId('login-email').fill(user.email)
  await page.getByTestId('login-password').locator('input').fill(user.password)
  await page.getByTestId('login-submit').click()
}

test('logs in and lands on the protected page', async ({ page }) => {
  await login(page, OWNER)

  await expect(page).toHaveURL('/')
  await expect(page.getByTestId('current-user')).toHaveText(OWNER.email)
})

test('a sole membership is selected without asking', async ({ page }) => {
  await login(page, OWNER)

  await expect(page.getByTestId('active-organization')).toHaveText(ALPHA)
})

test('invalid credentials show an error and stay on /login', async ({ page }) => {
  await goto(page, '/login')
  await page.getByTestId('login-email').fill(OWNER.email)
  await page.getByTestId('login-password').locator('input').fill('definitely-wrong')
  await page.getByTestId('login-submit').click()

  await expect(page.getByTestId('login-error')).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
})

test('client-side validation rejects a malformed email before any request', async ({ page }) => {
  await goto(page, '/login')
  await page.getByTestId('login-email').fill('not-an-email')
  await page.getByTestId('login-password').locator('input').fill('whatever')
  await page.getByTestId('login-submit').click()

  await expect(page.getByTestId('login-email-error')).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
})

test('an anonymous visitor is redirected and returned to where they were going', async ({
  page,
}) => {
  await page.goto('/')

  await expect(page).toHaveURL('/login?redirect=/')
})

test('reloading a protected page does not flash the login screen', async ({ page }) => {
  // The acceptance criterion of Issue 8, and only observable in a browser. The
  // assertion is on the *server's* response, before any hydration: if SSR did
  // not resolve the session, this HTML would be a redirect to /login.
  await login(page, OWNER)
  await expect(page).toHaveURL('/')

  const response = await page.reload()

  expect(response?.status()).toBe(200)
  expect(await response!.text()).toContain(OWNER.email)
  await expect(page).toHaveURL('/')
  await expect(page.getByTestId('current-user')).toHaveText(OWNER.email)
})

test('the server refuses to guess between two memberships', async ({ page }) => {
  await login(page, MULTI)

  await expect(page.getByTestId('active-organization')).toHaveText('не обрано')
})

test('selecting an organization survives a full page reload', async ({ page }) => {
  await login(page, MULTI)

  await page.getByTestId('org-selector').click()
  await page.getByRole('option', { name: BETA }).click()
  await expect(page.getByTestId('active-organization')).toHaveText(BETA)

  await page.reload()

  // It was never stored in the browser; it survives because the server owns it.
  await expect(page.getByTestId('active-organization')).toHaveText(BETA)
})

test('logging out clears the session and blocks protected routes', async ({ page }) => {
  await login(page, OWNER)
  await expect(page).toHaveURL('/')

  await page.getByTestId('logout').click()
  await expect(page).toHaveURL(/\/login/)

  await page.goto('/')
  await expect(page).toHaveURL('/login?redirect=/')
})

test('an authenticated visitor is bounced away from the login page', async ({ page }) => {
  await login(page, OWNER)
  await expect(page).toHaveURL('/')

  await page.goto('/login')

  await expect(page).toHaveURL('/')
})
