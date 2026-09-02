<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  acknowledgeFallAlert,
  fetchAlgorithmsStatus,
  fetchFallDetectionHistory,
} from '../api/algorithms'
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
const previewError = ref(false)
const previewVersion = ref(Date.now())
const history = ref<AlgorithmResult[]>([])
const historyPage = ref(1)
const acknowledging = ref(false)
const alertSuppressed = ref(false)
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
let refresh: ReturnType<typeof setInterval> | null = null

const worker = computed(() => latestWorkerStatus.value ?? initialWorker.value)
const result = computed(() => latestFallDetection.value ?? initialResult.value)
const runtime = computed<Record<string, unknown>>(() => {
  const value = worker.value?.runtime?.fall_detection
  return isRecord(value) ? value : {}
})
const classifiedStates = ['normal', 'suspected_fall', 'fallen', 'recovering']
const historyPageSize = 5
const transientStates = [
  'no_person',
  'low_pose_confidence',
  'warming_up',
  'waiting_for_media',
  'waiting_for_pose',
  'media_reconnecting',
]
const freshResult = computed(() => {
  const value = result.value
  return Boolean(
    value &&
      !value.simulated &&
      value.task === 'fall_detection' &&
      now.value - Date.parse(value.result_timestamp) < 15_000,
  )
})
const currentState = computed(() => {
  if (freshResult.value && result.value) {
    if (classifiedStates.includes(result.value.label)) return result.value.label

    // A few missing prone poses describe observation quality, not evidence
    // that a confirmed temporal fall has ended. Keep an active non-normal
    // decision until STGCN explicitly classifies recovery.
    const detectorState = result.value.metadata?.detector_state
    if (
      transientStates.includes(result.value.label) &&
      typeof detectorState === 'string' &&
      ['suspected_fall', 'fallen', 'recovering'].includes(detectorState)
    ) {
      return detectorState
    }
    return result.value.label
  }
  if (
    worker.value?.online === true &&
    worker.value.capabilities.fall_detection === 'running' &&
    typeof runtime.value.status === 'string'
  ) {
    return runtime.value.status
  }
  return 'unavailable'
})
const classifiedResult = computed(
  () =>
    freshResult.value &&
    classifiedStates.includes(currentState.value),
)
const observationWarning = computed(() => {
  const label = result.value?.label
  return freshResult.value && label && transientStates.includes(label) ? label : null
})
function stateLabelFor(state: string): string {
  return (
    {
    normal: '正常',
    suspected_fall: '疑似跌倒',
    fallen: '检测到跌倒',
    recovering: '恢复观察中',
    no_person: '未检测到人员',
    low_pose_confidence: '人体姿态识别不稳定',
    warming_up: '正在建立时序分析',
    waiting_for_media: '等待视频接入',
    waiting_for_pose: '等待人体姿态',
    media_reconnecting: '视频正在重连',
    media_unavailable: '视频暂时不可用',
    inference_error: '模型分析异常',
    runtime_error: '检测服务异常',
    unavailable: '检测不可用',
    }[state] ?? state.toUpperCase()
  )
}
const stateLabel = computed(() => stateLabelFor(currentState.value))
const stateTone = computed(() => {
  if (currentState.value === 'fallen') return 'danger'
  if (currentState.value === 'suspected_fall') return 'warning'
  if (currentState.value === 'normal') return 'success'
  return 'info'
})
const metadata = computed<Record<string, unknown>>(() => result.value?.metadata ?? {})
const fallScore = computed<number | null>(() => {
  if (!freshResult.value) return null
  if (typeof result.value?.score === 'number') return result.value.score
  const previousScore = metadata.value.last_fall_score
  return typeof previousScore === 'number' ? previousScore : null
})
const sequenceProgress = computed(() => {
  const value = metadata.value.sequence_progress ?? runtime.value.sequence_progress
  return typeof value === 'number' ? Math.round(Math.max(0, Math.min(1, value)) * 100) : null
})
const personDetectedLabel = computed(() => {
  const value = metadata.value.person_detected
  if (value === true) return '已检测到'
  if (value === false) return '未检测到'
  return '--'
})
const analysisFps = computed(() => metadata.value.processing_fps ?? metadata.value.pose_inference_fps)
const classifiedHistory = computed(() =>
  history.value.filter((item) => classifiedStates.includes(item.label)),
)
const historyPageCount = computed(() =>
  Math.max(1, Math.ceil(classifiedHistory.value.length / historyPageSize)),
)
const paginatedHistory = computed(() => {
  const start = (historyPage.value - 1) * historyPageSize
  return classifiedHistory.value.slice(start, start + historyPageSize)
})
const previewUrl = computed(
  () => `/api/fall-detection/preview.mjpeg?v=${previewVersion.value}`,
)
const alertSignal = computed(
  () =>
    metadata.value.alert_active === true ||
    runtime.value.alert_active === true,
)
const fallAlert = computed(() => alertSignal.value && !alertSuppressed.value)

watch(alertSignal, (active) => {
  // Returning to a non-alert state rearms the UI for the next incident.
  if (!active) alertSuppressed.value = false
})

function reconnectPreview(): void {
  previewError.value = false
  previewVersion.value = Date.now()
}

async function acknowledgeAlert(): Promise<void> {
  acknowledging.value = true
  try {
    await acknowledgeFallAlert()
    alertSuppressed.value = true
    await loadStatus()
  } finally {
    acknowledging.value = false
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function display(value: unknown, suffix = ''): string {
  if (typeof value === 'number') return `${Number(value.toFixed(2))}${suffix}`
  if (typeof value === 'string' && value) return `${value}${suffix}`
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return '--'
}

function formatFallScore(value: number | null): string {
  return value === null ? '--' : `${(value * 100).toFixed(1)}`
}

function historyTone(label: string): 'success' | 'warning' | 'danger' | 'info' {
  if (label === 'fallen') return 'danger'
  if (label === 'suspected_fall') return 'warning'
  if (label === 'normal') return 'success'
  return 'info'
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
    history.value = await fetchFallDetectionHistory(100)
    historyPage.value = Math.min(historyPage.value, historyPageCount.value)
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
    />

    <section v-if="fallAlert" class="fall-alert" role="alert">
      <div><strong>检测到跌倒</strong><span>请立即确认现场情况。告警至少保留 15 秒，人工确认可提前关闭。</span></div>
      <button type="button" :disabled="acknowledging" @click="acknowledgeAlert">
        {{ acknowledging ? '正在确认...' : '确认已处理' }}
      </button>
    </section>

    <p v-if="loadError" class="fall-notice fall-notice--error">跌倒检测状态暂时不可获取</p>

    <section class="fall-live-grid">
      <article class="panel-card analysis-view">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">AI ANALYSIS VIEW</span><h2>人物与骨架分析画面</h2></div>
          <div class="analysis-view__actions">
            <el-tag :type="previewError ? 'danger' : 'success'" effect="plain">
              {{ previewError ? '画面离线' : '检测画面' }}
            </el-tag>
            <el-button
              :icon="Refresh"
              circle
              title="刷新检测画面"
              aria-label="刷新检测画面"
              @click="reconnectPreview"
            />
          </div>
        </div>
        <div class="analysis-canvas" :class="{ 'analysis-canvas--alert': fallAlert }">
          <div v-if="fallAlert" class="analysis-canvas__alert" role="alert">
            检测到跌倒 · 请立即确认现场情况
          </div>
          <img
            :key="previewVersion"
            :src="previewUrl"
            alt="H6c AI 人物与 COCO17 骨架分析画面"
            @load="previewError = false"
            @error="previewError = true"
          />
          <div v-if="previewError" class="analysis-canvas__empty">
            <strong>AI 分析画面暂时不可用</strong>
            <span>检测结果管道会独立继续运行，可点击刷新按钮重新获取画面。</span>
          </div>
        </div>
      </article>

      <div class="fall-side-column">
        <article class="panel-card current-state">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">CURRENT DETECTION</span><h2>当前检测</h2></div>
          <el-tag :type="stateTone" effect="dark">{{ stateLabel }}</el-tag>
        </div>
        <strong class="current-state__value">{{ stateLabel }}</strong>
        <p>
          {{ classifiedResult
            ? '跌倒检测持续运行中'
            : currentState === 'warming_up'
              ? `正在积累连续动作信息${sequenceProgress === null ? '' : `（${sequenceProgress}%）`}`
              : '正在等待可用于判断的连续人体动作' }}
        </p>
        <p v-if="observationWarning" class="current-state__observation">
          当前观测：{{ stateLabelFor(observationWarning) }}。姿态短时丢失不会清除已确认的时序跌倒状态。
        </p>
        <div class="current-state__links">
          <router-link to="/dashboard">查看实时视频</router-link>
          <span>Realtime: {{ realtimeStatus }}</span>
        </div>
        </article>

        <article class="panel-card fall-metrics">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">DETECTION METRICS</span><h2>检测指标</h2></div>
          <el-tag :type="worker?.online ? 'success' : 'info'" effect="plain">
            {{ worker?.online ? 'online' : 'offline' }}
          </el-tag>
        </div>
        <div class="metric-grid">
          <div><span>Fall Score</span><strong>{{ formatFallScore(fallScore) }}</strong></div>
          <div><span>人物检测</span><strong>{{ personDetectedLabel }}</strong></div>
          <div><span>骨架置信度</span><strong>{{ display(metadata.keypoint_confidence) }}</strong></div>
          <div><span>分析帧率</span><strong>{{ display(analysisFps, ' FPS') }}</strong></div>
          <div><span>分析耗时</span><strong>{{ display(result?.latency_ms, ' ms') }}</strong></div>
          <div><span>最近更新</span><strong class="metric-grid__time">{{ formatTime(result?.result_timestamp) }}</strong></div>
        </div>
        </article>
      </div>
    </section>

    <section class="panel-card fall-history">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">DETECTION HISTORY</span><h2>检测状态记录</h2></div>
        <el-tag effect="plain">共 {{ classifiedHistory.length }} 条</el-tag>
      </div>
      <el-empty v-if="classifiedHistory.length === 0" description="暂无检测状态记录" />
      <template v-else>
        <ol>
        <li v-for="item in paginatedHistory" :key="item.result_id">
          <el-tag :type="historyTone(item.label)" effect="plain">
            {{ stateLabelFor(item.label) }}
          </el-tag>
          <span>{{ formatTime(item.result_timestamp) }}</span>
          <span>Fall Score {{ formatFallScore(item.score) }}</span>
        </li>
        </ol>
        <div class="history-pagination-row">
          <span>第 {{ historyPage }} / {{ historyPageCount }} 页</span>
          <el-pagination
            v-model:current-page="historyPage"
            class="history-pagination"
            background
            layout="prev, pager, next, jumper"
            :page-size="historyPageSize"
            :pager-count="5"
            :total="classifiedHistory.length"
          />
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.fall-notice { margin: -8px 0 18px; padding: 11px 14px; border: 1px solid var(--color-warning-border); border-radius: 9px; color: var(--color-warning-text); background: var(--color-warning-soft); font-size: 13px; }
.fall-notice--error { border-color: var(--color-danger-border); color: var(--color-danger-text); background: var(--color-danger-soft); }
.fall-alert { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: -8px 0 18px; padding: 16px 20px; border: 1px solid #d93838; border-radius: 10px; color: #fff; background: #bd2525; box-shadow: 0 10px 24px rgba(189, 37, 37, .2); }
.fall-alert div { display: grid; gap: 4px; }
.fall-alert strong { font-size: 20px; }
.fall-alert button { padding: 9px 15px; border: 1px solid rgba(255,255,255,.65); border-radius: 7px; color: #8e1717; background: #fff; font-weight: 700; cursor: pointer; }
.fall-live-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(340px, .75fr); align-items: start; gap: 20px; margin-bottom: 20px; }
.analysis-view { min-width: 0; }
.fall-side-column { display: grid; min-width: 0; grid-template-rows: auto auto; align-content: start; gap: 20px; }
.analysis-view__actions { display: flex; align-items: center; gap: 10px; }
.analysis-canvas { position: relative; display: grid; margin-top: 14px; overflow: hidden; place-items: center; aspect-ratio: 16 / 9; border: 1px solid #273a35; border-radius: 10px; background: #0b1110; }
.analysis-canvas--alert { border: 3px solid #d93838; }
.analysis-canvas img { display: block; width: 100%; height: 100%; object-fit: contain; }
.analysis-canvas__alert { position: absolute; z-index: 2; top: 0; right: 0; left: 0; padding: 9px 16px; color: #fff; background: rgba(190, 28, 28, .94); font-size: 14px; font-weight: 750; text-align: center; letter-spacing: .02em; }
.analysis-canvas__empty { position: absolute; inset: 0; display: grid; align-content: center; justify-items: center; gap: 8px; color: #d9e6e1; background: #0b1110; }
.analysis-canvas__empty span { color: #91a69e; font-size: 13px; }
.current-state, .fall-metrics { min-height: 0; }
.current-state__value { display: block; margin-top: 18px; color: var(--color-heading); font-size: 32px; letter-spacing: .04em; }
.current-state > p { margin: 8px 0 16px; color: var(--color-text-secondary); font-size: 13px; }
.current-state > p.current-state__observation { margin-top: -8px; color: var(--color-warning); font-size: 12px; }
.current-state__links { display: flex; justify-content: space-between; color: var(--color-text-muted); font-size: 12px; }
.current-state__links a { color: var(--color-primary); font-weight: 650; }
.metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-top: 14px; }
.metric-grid > div { min-width: 0; padding: 10px 12px; border: 1px solid var(--color-border-light); border-radius: 9px; background: var(--color-surface-soft); }
.metric-grid span { display: block; color: var(--color-text-muted); font-size: 11px; }
.metric-grid strong { display: block; overflow: hidden; margin-top: 6px; color: var(--color-heading); font-size: 17px; text-overflow: ellipsis; white-space: nowrap; }
.metric-grid strong.metric-grid__time { font-size: 12px; }
.fall-history { margin-top: 20px; }
.fall-history ol { display: grid; gap: 0; margin: 18px 0 0; padding: 0; list-style: none; }
.fall-history li { display: grid; grid-template-columns: 150px 1fr 120px; align-items: center; gap: 14px; padding: 11px 0; border-bottom: 1px solid var(--color-border-light); color: var(--color-text-secondary); font-size: 13px; }
.history-pagination-row { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-top: 10px; color: var(--color-text-secondary); font-size: 12px; }
.history-pagination { justify-content: flex-end; }
.history-pagination :deep(.btn-prev), .history-pagination :deep(.btn-next), .history-pagination :deep(.el-pager li) { border: 1px solid var(--color-border); background: var(--color-control-bg) !important; }
.history-pagination :deep(.el-pager li.is-active) { border-color: var(--color-primary); color: #fff; background: var(--color-primary) !important; }
@media (max-width: 980px) {
  .fall-live-grid { grid-template-columns: 1fr; }
  .fall-side-column { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: auto; }
}
@media (max-width: 760px) {
  .fall-side-column { grid-template-columns: 1fr; }
  .fall-alert { align-items: flex-start; flex-direction: column; }
}
</style>
