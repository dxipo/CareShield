<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchSystemStatus, type SystemStatus } from '../api/algorithms'
import BackendStatusPanel from '../components/BackendStatusPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { lastRealtimeMessageAt, realtimeStatus } from '../realtime'

const systemStatus = ref<SystemStatus | null>(null)
const loadError = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const realtimeLabel = computed(() =>
  realtimeStatus.value === 'connected' ? 'Connected' : 'Disconnected',
)

async function loadStatus() {
  try {
    systemStatus.value = await fetchSystemStatus()
    loadError.value = false
  } catch {
    loadError.value = true
  }
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
}

onMounted(() => {
  void loadStatus()
  refreshTimer = setInterval(loadStatus, 10_000)
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="SYSTEM STATUS"
      title="系统状态"
      description="查看 Backend、Redis、AI Worker 与浏览器实时通道的真实运行状态。"
    />

    <p v-if="loadError" class="system-error">实时基础设施状态暂时不可用</p>
    <section class="system-grid">
      <BackendStatusPanel />
      <article class="panel-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">AI & REALTIME</span><h2>实时基础设施</h2></div>
        </div>
        <dl class="system-list">
          <div><dt>Redis</dt><dd :class="{ online: systemStatus?.redis === 'healthy' }">{{ systemStatus?.redis ?? '--' }}</dd></div>
          <div><dt>AI Worker</dt><dd :class="{ online: systemStatus?.ai_worker === 'online' }">{{ systemStatus?.ai_worker ?? '--' }}</dd></div>
          <div><dt>Realtime Channel</dt><dd :class="{ online: realtimeStatus === 'connected' }">{{ realtimeLabel }}</dd></div>
          <div><dt>Last Realtime Message</dt><dd>{{ formatTime(lastRealtimeMessageAt) }}</dd></div>
        </dl>
      </article>
    </section>
  </div>
</template>

<style scoped>
.system-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.system-list { margin: 18px 0 0; }
.system-list div { display: flex; justify-content: space-between; gap: 20px; padding: 14px 0; border-bottom: 1px solid var(--color-border-light); }
.system-list div:last-child { border-bottom: 0; }
.system-list dt { color: var(--color-text-secondary); }
.system-list dd { margin: 0; color: var(--color-text-muted); font-weight: 650; }
.system-list dd.online { color: var(--color-success); }
.system-error { margin: -10px 0 18px; color: var(--color-danger); }
</style>
