// The API is reachable at two different URLs depending on who is asking:
// server-side rendering runs inside the container (http://api:8000), while the
// browser reaches it on a published host port. Rather than juggling both, Nitro
// proxies /api/v1/** to the API service, so every caller — SSR and client alike
// — uses the same same-origin path and no request has to know which side it is on.
const apiInternalUrl = process.env.NUXT_API_INTERNAL_URL || 'http://api:8000'

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },

  // Design tokens are global rather than per-page scoped styles: five pages
  // each carrying their own copy of the palette is how three slightly
  // different greys end up shipping.
  css: ['~/assets/css/tokens.css'],

  runtimeConfig: {
    public: {
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL || '/api/v1',
    },
  },

  nitro: {
    routeRules: {
      '/api/v1/**': { proxy: `${apiInternalUrl}/api/v1/**` },
    },
  },
})
