import tailwindcss from '@tailwindcss/vite'
import Aura from '@primeuix/themes/aura'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // The PRD lists SSR as a technical constraint (offline mode is deferred);
  // stated explicitly so it survives a future config edit.
  ssr: true,

  modules: ['@nuxt/eslint', '@pinia/nuxt', '@primevue/nuxt-module'],

  css: ['~/assets/css/main.css'],

  vite: {
    plugins: [tailwindcss()],
  },

  typescript: {
    strict: true,
    // Typecheck runs as its own gate (`pnpm typecheck`), not on every dev build.
    typeCheck: false,
  },

  primevue: {
    options: {
      theme: {
        preset: Aura,
        options: { darkModeSelector: '.dark' },
      },
    },
  },

  runtimeConfig: {
    public: {
      // Overridden at runtime by NUXT_PUBLIC_API_BASE.
      apiBase: 'http://localhost:8000/api/v1',
    },
  },
})
