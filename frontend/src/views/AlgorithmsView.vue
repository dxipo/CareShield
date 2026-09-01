<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import PageHeader from '../components/PageHeader.vue'
import {
  lastRealtimeMessageAt,
  latestPipelineLatencyMs,
  latestPipelineTest,
  latestWorkerStatus,
  realtimeStatus,
} from '../realtime'
import type { AlgorithmCapabilities, WorkerStatus } from '../realtime/types'

const defaultCapabilities: AlgorithmCapabilities = {
  fall_detection: 'not_installed',
  fall_risk: 'not_installed',
  fraud_detection: 'not_installed',
}

const worker = ref<WorkerStatus | null>(null)
const capabilities = ref(defaultCapabilities)
const redisReachable = ref(false)
const loading = ref(true)
const loadError = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const activeWorker = computed(() => latestWorkerStatus.value ?? worker.value)
// Each independent worker reports its own capability and correctly marks the
// other algorithms as not_installed. Model availability must therefore use
// the Backend aggregate instead of whichever worker heartbeat arrived last.
const activeCapabilities = computed(() => capabilities.value)
const socketLabel = computed(() =>
  realtimeStatus.value === 'connected' ? 'Connected' : 'Disconnected',
)

function formatTime(value: string | null | undefined): string {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    hour12: false,
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

function capabilityLabel(value: string): string {
  return {
    not_installed: 'Not Installed',
    installed: 'Installed',
    starting: 'Starting',
    running: 'Running',
    unavailable: 'Unavailable',
    error: 'Error',
  }[value] ?? value
}

function capabilityTag(value: string): 'success' | 'warning' | 'danger' | 'info' {
  if (value === 'running') return 'success'
  if (value === 'starting' || value === 'installed') return 'warning'
  if (value === 'unavailable' || value === 'error') return 'danger'
  return 'info'
}

async function loadStatus() {
  try {
    const response = await fetchAlgorithmsStatus()
    worker.value = response.workers[0] ?? null
    capabilities.value = response.capabilities
    redisReachable.value = response.redis_reachable
    if (!latestPipelineTest.value && response.latest_pipeline_test?.simulated) {
      latestPipelineTest.value = response.latest_pipeline_test
    }
    loadError.value = false
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
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
      eyebrow="AI INFRASTRUCTURE"
      title="算法管理"
      description="查看 AI Worker、统一实时通道与已接入算法能力状态。"
    />

    <div v-if="loadError" class="status-notice status-notice--error">算法基础设施状态暂时不可用</div>

    <section class="algorithm-grid" :aria-busy="loading">
      <article class="panel-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">AI WORKER</span><h2>Worker 状态</h2></div>
          <el-tag :type="activeWorker?.online ? 'success' : 'info'" effect="plain">
            {{ activeWorker?.online ? 'Online' : 'Offline' }}
          </el-tag>
        </div>
        <dl class="status-list">
          <div><dt>Worker ID</dt><dd>{{ activeWorker?.worker_id ?? '--' }}</dd></div>
          <div><dt>Service Version</dt><dd>{{ activeWorker?.version ?? '--' }}</dd></div>
          <div><dt>Last Heartbeat</dt><dd>{{ formatTime(activeWorker?.timestamp) }}</dd></div>
          <div><dt>Redis State</dt><dd>{{ redisReachable ? 'Healthy' : 'Unavailable' }}</dd></div>
        </dl>
      </article>

      <article class="panel-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">REALTIME CHANNEL</span><h2>WebSocket</h2></div>
          <el-tag :type="realtimeStatus === 'connected' ? 'success' : 'info'" effect="plain">
            {{ socketLabel }}
          </el-tag>
        </div>
        <dl class="status-list">
          <div><dt>Endpoint</dt><dd>/ws/realtime</dd></div>
          <div><dt>Connection</dt><dd>{{ realtimeStatus }}</dd></div>
          <div><dt>Last Message</dt><dd>{{ formatTime(lastRealtimeMessageAt) }}</dd></div>
          <div><dt>Channel Policy</dt><dd>Unified</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel-card algorithm-capabilities">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">ALGORITHM CAPABILITIES</span><h2>模型能力</h2></div>
        <span class="panel-card__hint">状态由 Backend 聚合在线 Worker 心跳</span>
      </div>
      <div class="capability-grid">
        <div><strong>Fall Detection</strong><el-tag :type="capabilityTag(activeCapabilities.fall_detection)" effect="plain">{{ capabilityLabel(activeCapabilities.fall_detection) }}</el-tag></div>
        <div><strong>Fall Risk</strong><el-tag :type="capabilityTag(activeCapabilities.fall_risk)" effect="plain">{{ capabilityLabel(activeCapabilities.fall_risk) }}</el-tag></div>
        <div><strong>Fraud Detection</strong><el-tag :type="capabilityTag(activeCapabilities.fraud_detection)" effect="plain">{{ capabilityLabel(activeCapabilities.fraud_detection) }}</el-tag></div>
      </div>
    </section>

    <section class="panel-card pipeline-panel">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">DEVELOPER DIAGNOSTICS</span><h2>Pipeline Test</h2></div>
        <el-tag v-if="latestPipelineTest" type="warning" effect="plain">Simulated</el-tag>
      </div>
      <div v-if="latestPipelineTest" class="pipeline-result">
        <strong>{{ latestPipelineTest.label }}</strong>
        <span>Task: {{ latestPipelineTest.task }}</span>
        <span>Received: {{ formatTime(lastRealtimeMessageAt ?? latestPipelineTest.result_timestamp) }}</span>
        <span>End-to-end: {{ latestPipelineLatencyMs ?? 'Unavailable' }} ms</span>
      </div>
      <p v-else class="empty-copy">尚未收到开发用 pipeline_test。该测试不会进入风险业务页面或事件中心。</p>
    </section>
  </div>
</template>

<style scoped>
.algorithm-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-bottom: 20px; }
.algorithm-capabilities { margin-bottom: 20px; }
.status-list { margin: 18px 0 0; }
.status-list div { display: flex; justify-content: space-between; gap: 20px; padding: 13px 0; border-bottom: 1px solid var(--color-border-light); }
.status-list div:last-child { border-bottom: 0; }
.status-list dt { color: var(--color-text-secondary); }
.status-list dd { margin: 0; color: var(--color-heading); font-weight: 650; text-align: right; }
.capability-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.capability-grid > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 17px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.pipeline-result { display: flex; flex-wrap: wrap; gap: 24px; margin-top: 20px; color: var(--color-text-secondary); }
.pipeline-result strong { color: var(--color-heading); }
.empty-copy { margin: 22px 0 2px; color: var(--color-text-muted); }
.status-notice { margin: -12px 0 18px; padding: 10px 14px; border-radius: 8px; }
.status-notice--error { color: var(--color-danger-text); background: var(--color-danger-soft); }
</style>
