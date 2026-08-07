export default defineEventHandler(() => {
  return {
    status: 'ok',
    service: 'my-pain-radar-web',
    timestamp: new Date().toISOString(),
  }
})
