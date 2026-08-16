<script setup lang="ts">
import { onMounted, ref } from 'vue'

interface HealthResponse {
  status: string
  service: string
}

const backendHealth = ref<HealthResponse | null>(null)
const backendError = ref('')
const isLoading = ref(true)

onMounted(async () => {
  try {
    const response = await fetch('/api/health')

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    backendHealth.value = (await response.json()) as HealthResponse
  } catch (error) {
    backendError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <main class="status-card">
    <p class="eyebrow">颐安盾 · M0</p>
    <h1>Elderly AI Safety Platform</h1>

    <dl class="status-list">
      <div>
        <dt>Frontend Status</dt>
        <dd class="ok">OK</dd>
      </div>
      <div>
        <dt>Backend Status</dt>
        <dd v-if="isLoading">Checking…</dd>
        <dd v-else-if="backendHealth" class="ok">
          {{ backendHealth.status }} · {{ backendHealth.service }}
        </dd>
        <dd v-else class="error">Unavailable · {{ backendError }}</dd>
      </div>
    </dl>
  </main>
</template>
