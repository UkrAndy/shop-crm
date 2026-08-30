<script setup lang="ts">
import { z } from 'zod'

const route = useRoute()
const session = useSessionStore()

// Mirrors the server's rules so the user is told immediately, but it is not a
// substitute for them: the backend validates the same body with Pydantic and
// answers 422 in the shared envelope regardless of what the client checked.
const loginSchema = z.object({
  // `z.email()`, not the deprecated `z.string().email()` — Zod 4 moved string
  // formats to top-level schemas.
  email: z.email('Введіть коректний email'),
  password: z.string().min(1, 'Введіть пароль'),
})

const email = ref('')
const password = ref('')
const fieldErrors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const submitting = ref(false)

async function onSubmit() {
  fieldErrors.value = {}
  formError.value = null

  const parsed = loginSchema.safeParse({ email: email.value, password: password.value })
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      const field = String(issue.path[0] ?? '')
      // Keep the first message per field; a stack of them helps nobody.
      if (field && !fieldErrors.value[field]) fieldErrors.value[field] = issue.message
    }
    return
  }

  submitting.value = true
  try {
    await session.login(parsed.data.email, parsed.data.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await navigateTo(redirect)
  }
  catch (error) {
    // The server deliberately gives one message for a wrong password and an
    // unknown email; showing it verbatim keeps that property intact.
    formError.value = apiErrorMessage(error, 'Не вдалося увійти. Спробуйте ще раз.')
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-8">
    <h1 class="text-xl font-semibold">
      Вхід до TestVasja
    </h1>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <div class="flex flex-col gap-1">
        <label for="email" class="text-sm font-medium">Email</label>
        <InputText
          id="email"
          v-model="email"
          data-testid="login-email"
          type="email"
          autocomplete="username"
          :invalid="Boolean(fieldErrors.email)"
        />
        <small v-if="fieldErrors.email" data-testid="login-email-error" class="text-red-600">
          {{ fieldErrors.email }}
        </small>
      </div>

      <div class="flex flex-col gap-1">
        <label for="password" class="text-sm font-medium">Пароль</label>
        <Password
          v-model="password"
          input-id="password"
          data-testid="login-password"
          :feedback="false"
          toggle-mask
          fluid
          autocomplete="current-password"
          :invalid="Boolean(fieldErrors.password)"
        />
        <small v-if="fieldErrors.password" data-testid="login-password-error" class="text-red-600">
          {{ fieldErrors.password }}
        </small>
      </div>

      <Message v-if="formError" data-testid="login-error" severity="error" :closable="false">
        {{ formError }}
      </Message>

      <Button
        type="submit"
        data-testid="login-submit"
        label="Увійти"
        :loading="submitting"
      />
    </form>
  </main>
</template>
