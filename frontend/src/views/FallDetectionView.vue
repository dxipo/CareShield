<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import PageHeader from '../components/PageHeader.vue'
import {
  latestFallDetection,
  latestWorkerStatus,
  realtimeStatus,
} from '../realtime'
import type { AlgorithmResult, WorkerStatus } from '../realtime/types'

const initialWorker = ref<WorkerStatus | null>(null)
const initialResult = ref<AlgorithmResult | null>(null)
const loadError = ref(false)
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
let refresh: ReturnType<typeof setInterval> | null = null

const worker = computed(() => latestWorkerStatus.value ?? initialWorker.value)
const result = computed(() => latestFallDetection.value ?? initialResult.value)
const runtime = computed<Record<string, unknown>>(() => {
  const value = worker.value?.runtime?.fall_detection
  return isRecord(value) ? value : {}
})
const freshResult = computed(() => {
  const value = result.value
  return Boolean(
    value &&
      !value.simulated &&
      value.task === 'fall_detection' &&
      now.value - Date.parse(value.result_timestamp) < 15_000,
  )
})
const available = computed(
  () =>
    worker.value?.online === true &&
    worker.value.capabilities.fall_detection === 'running' &&
    freshResult.value,
)
const stateLabel = computed(() => {
  if (!available.value || !result.value) return 'UNAVAILABLE'
  return {
    normal: 'NORMAL',
    suspected_fall: 'SUSPECTED FALL',
    fallen: 'FALLEN',
    recovering: 'RECOVERING',
    no_person: 'NO PERSON',
    low_pose_confidence: 'LOW POSE CONFIDENCE',
  }[result.value.label] ?? result.value.label.toUpperCase()
})
const stateTone = computed(() => {
  if (!available.value) return 'info'
  if (result.value?.label === 'fallen') return 'danger'
  if (result.value?.label === 'suspected_fall') return 'warning'
  if (result.value?.label === 'normal') return 'success'
  return 'info'
})
const metadata = computed<Record<string, unknown>>(() => result.value?.metadata ?? {})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function display(value: unknown, suffix = ''): string {
  if (typeof value === 'number') return `${Number(value.toFixed(2))}${suffix}`
  if (typeof value === 'string' && value) return `${value}${suffix}`
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return '--'
}

function formatTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
}

async function loadStatus(): Promise<void> {
  try {
    const snapshot = await fetchAlgorithmsStatus()
    initialWorker.value = snapshot.workers[0] ?? null
    if (
      snapshot.latest_fall_detection?.task === 'fall_detection' &&
      snapshot.latest_fall_detection.simulated === false
    ) {
      initialResult.value = snapshot.latest_fall_detection
    }
    loadError.value = false
  } catch {
    loadError.value = true
  }
}

onMounted(() => {
  void loadStatus()
  clock = setInterval(() => (now.value = Date.now()), 1_000)
  refresh = setInterval(loadStatus, 10_000)
})

onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
  if (refresh) clearInterval(refresh)
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="REAL FALL DETECTION"
      title="实时跌倒检测"
      description="真实 H6c 视频由独立 AI Worker 解码并执行 GPU 姿态与时序检测；视频画面和结果面板不承诺逐帧同步。"
    />

    <p v-if="loadError" class="fall-notice fall-notice--error">跌倒检测状态暂时不可获取</p>
    <p class="fall-notice">
      M5 为工程基线启发式算法，尚未经过临床验证。系统不可用或未检测到人员时不会自动显示“正常”。
    </p>

    <section class="fall-overview-grid">
      <article class="panel-card current-state">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">CURRENT DETECTION</span><h2>当前检测</h2></div>
          <el-tag :type="stateTone" effect="dark">{{ stateLabel }}</el-tag>
        </div>
        <strong class="current-state__value">{{ stateLabel }}</strong>
        <p>
          {{ available ? '结果来自真实视频与真实模型，simulated=false' : 'Fall Detection unavailable' }}
        </p>
        <div class="current-state__links">
          <router-link to="/monitor">查看实时视频</router-link>
          <span>Realtime: {{ realtimeStatus }}</span>
        </div>
      </article>

      <article class="panel-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">RUNTIME</span><h2>Worker 与模型</h2></div>
          <el-tag :type="worker?.online ? 'success' : 'info'" effect="plain">
            {{ worker?.online ? 'Worker Online' : 'Worker Offline' }}
          </el-tag>
        </div>
        <dl class="fall-list">
          <div><dt>Detector</dt><dd>{{ display(runtime.status) }}</dd></div>
          <div><dt>GPU</dt><dd>{{ display(runtime.gpu_name) }}</dd></div>
          <div><dt>AI Device</dt><dd>{{ display(runtime.device) }}</dd></div>
          <div><dt>Model</dt><dd>{{ display(runtime.model) }}</dd></div>
          <div><dt>Model Version</dt><dd>{{ display(runtime.model_version) }}</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel-card fall-metrics">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">REALTIME METRICS</span><h2>检测指标</h2></div>
        <span class="panel-card__hint">最近更新：{{ formatTime(result?.result_timestamp) }}</span>
      </div>
      <div class="metric-grid">
        <div><span>Fall Score</span><strong>{{ display(result?.score) }}</strong><small>heuristic, not probability</small></div>
        <div><span>Person Detected</span><strong>{{ display(metadata.person_detected) }}</strong><small>真实姿态结果</small></div>
        <div><span>Keypoint Confidence</span><strong>{{ display(metadata.keypoint_confidence) }}</strong><small>mean confidence</small></div>
        <div><span>Source FPS</span><strong>{{ display(metadata.source_fps) }}</strong><small>camera stream</small></div>
        <div><span>Sample FPS</span><strong>{{ display(metadata.sample_fps) }}</strong><small>frame sampler</small></div>
        <div><span>Inference FPS</span><strong>{{ display(metadata.inference_fps) }}</strong><small>pose inference</small></div>
        <div><span>AI Latency</span><strong>{{ display(result?.latency_ms, ' ms') }}</strong><small>pose + detector</small></div>
        <div><span>Detector Latency</span><strong>{{ display(metadata.detector_latency_ms, ' ms') }}</strong><small>feature + state machine</small></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.fall-notice { margin: -8px 0 18px; padding: 11px 14px; border: 1px solid #eadbbf; border-radius: 9px; color: #755a2c; background: #fffaf0; font-size: 13px; }
.fall-notice--error { border-color: #efd2cf; color: var(--color-danger); background: #fff3f1; }
.fall-overview-grid { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 20px; margin-bottom: 20px; }
.current-state__value { display: block; margin-top: 32px; color: var(--color-heading); font-size: 38px; letter-spacing: .04em; }
.current-state > p { margin: 10px 0 28px; color: var(--color-text-secondary); }
.current-state__links { display: flex; justify-content: space-between; color: var(--color-text-muted); font-size: 12px; }
.current-state__links a { color: var(--color-primary); font-weight: 650; }
.fall-list { margin: 18px 0 0; }
.fall-list div { display: flex; justify-content: space-between; gap: 18px; padding: 12px 0; border-bottom: 1px solid var(--color-border-light); }
.fall-list div:last-child { border: 0; }
.fall-list dt { color: var(--color-text-secondary); }
.fall-list dd { margin: 0; color: var(--color-heading); font-weight: 650; text-align: right; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.metric-grid > div { padding: 17px; border: 1px solid var(--color-border-light); border-radius: 10px; background: #f8faf9; }
.metric-grid span, .metric-grid small { display: block; color: var(--color-text-muted); font-size: 11px; }
.metric-grid strong { display: block; margin: 10px 0 7px; color: var(--color-heading); font-size: 21px; }
@media (max-width: 1350px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
