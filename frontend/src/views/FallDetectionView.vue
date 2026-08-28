<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

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
const acknowledging = ref(false)
const acknowledgedResultId = ref<string | null>(null)
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
    normal: 'NORMAL',
    suspected_fall: 'SUSPECTED FALL',
    fallen: 'FALLEN',
    recovering: 'RECOVERING',
    no_person: 'NO PERSON',
    low_pose_confidence: 'LOW POSE CONFIDENCE',
    warming_up: 'WARMING UP',
    waiting_for_media: 'WAITING FOR MEDIA',
    waiting_for_pose: 'WAITING FOR POSE',
    media_reconnecting: 'MEDIA RECONNECTING',
    media_unavailable: 'MEDIA UNAVAILABLE',
    inference_error: 'INFERENCE ERROR',
    runtime_error: 'RUNTIME ERROR',
    unavailable: 'UNAVAILABLE',
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
const previewUrl = computed(
  () => `/api/fall-detection/preview.mjpeg?v=${previewVersion.value}`,
)
const fallAlert = computed(
  () =>
    freshResult.value &&
    metadata.value.alert_active === true &&
    result.value?.result_id !== acknowledgedResultId.value,
)

function reconnectPreview(): void {
  previewError.value = false
  previewVersion.value = Date.now()
}

async function acknowledgeAlert(): Promise<void> {
  acknowledging.value = true
  try {
    await acknowledgeFallAlert()
    acknowledgedResultId.value = result.value?.result_id ?? null
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
    history.value = await fetchFallDetectionHistory(20)
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
      description="AI Worker 从真实 H6c 媒体中提取人物框与 COCO17 骨架，并由 STGCN-Extend 执行跌倒二分类。"
    />

    <section v-if="fallAlert" class="fall-alert" role="alert">
      <div><strong>检测到跌倒</strong><span>请立即确认现场情况。告警会保留到人工确认。</span></div>
      <button type="button" :disabled="acknowledging" @click="acknowledgeAlert">
        {{ acknowledging ? '正在确认...' : '确认已处理' }}
      </button>
    </section>

    <p v-if="loadError" class="fall-notice fall-notice--error">跌倒检测状态暂时不可获取</p>
    <p class="fall-notice">
      当前模型是论文 STGCN-Extend 工程基线，输出分数尚未校准为临床概率。系统不可用或未检测到人员时不会自动显示“正常”。
    </p>

    <section class="panel-card analysis-view">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">AI ANALYSIS VIEW</span><h2>人物与骨架分析画面</h2></div>
        <div class="analysis-view__actions">
          <el-tag :type="previewError ? 'danger' : 'success'" effect="plain">
            {{ previewError ? 'Preview Offline' : 'AI Preview' }}
          </el-tag>
          <button type="button" class="preview-reconnect" @click="reconnectPreview">重新连接</button>
        </div>
      </div>
      <div class="analysis-canvas" :class="{ 'analysis-canvas--alert': fallAlert }">
        <img
          :key="previewVersion"
          :src="previewUrl"
          alt="H6c AI 人物与 COCO17 骨架分析画面"
          @load="previewError = false"
          @error="previewError = true"
        />
        <div v-if="previewError" class="analysis-canvas__empty">
          <strong>AI 分析画面暂时不可用</strong>
          <span>检测结果管道会独立继续运行，可点击重新连接。</span>
        </div>
      </div>
      <p class="analysis-view__note">
        该画面由 AI Worker 在实际推理帧上绘制，因此人物框和骨架与算法输入一致；原始低延迟视频及声音仍可在
        <router-link to="/monitor">实时监测</router-link> 中查看。
      </p>
    </section>

    <section class="fall-overview-grid">
      <article class="panel-card current-state">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">CURRENT DETECTION</span><h2>当前检测</h2></div>
          <el-tag :type="stateTone" effect="dark">{{ stateLabel }}</el-tag>
        </div>
        <strong class="current-state__value">{{ stateLabel }}</strong>
        <p>
          {{ classifiedResult ? '结果来自真实视频与 STGCN 模型，simulated=false' : '正在等待可分类的连续骨架序列，当前不会显示为“正常”' }}
        </p>
        <p v-if="observationWarning" class="current-state__observation">
          当前观测：{{ stateLabelFor(observationWarning) }}。姿态短时丢失不会清除已确认的时序跌倒状态。
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
          <div><dt>Classifier</dt><dd>{{ display(runtime.model) }}</dd></div>
          <div><dt>Pose Model</dt><dd>{{ display(runtime.pose_model) }}</dd></div>
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
        <div><span>Fall Score</span><strong>{{ display(result?.score) }}</strong><small>uncalibrated STGCN score</small></div>
        <div><span>Person Detected</span><strong>{{ display(metadata.person_detected) }}</strong><small>真实姿态结果</small></div>
        <div><span>Keypoint Confidence</span><strong>{{ display(metadata.keypoint_confidence) }}</strong><small>mean confidence</small></div>
        <div><span>Source FPS</span><strong>{{ display(metadata.source_fps) }}</strong><small>camera stream</small></div>
        <div><span>Sample FPS</span><strong>{{ display(metadata.sample_fps) }}</strong><small>frame sampler</small></div>
        <div><span>Processing FPS</span><strong>{{ display(metadata.processing_fps) }}</strong><small>decode + pose throughput</small></div>
        <div><span>Pose Inference FPS</span><strong>{{ display(metadata.pose_inference_fps) }}</strong><small>pose inference</small></div>
        <div><span>AI Latency</span><strong>{{ display(result?.latency_ms, ' ms') }}</strong><small>pose + detector</small></div>
        <div><span>STGCN Latency</span><strong>{{ display(metadata.classifier_inference_ms, ' ms') }}</strong><small>binary classifier</small></div>
      </div>
    </section>

    <section class="panel-card fall-history">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">RECENT STATE HISTORY</span><h2>最近检测状态</h2></div>
        <span class="panel-card__hint">仅保留真实状态变化，不包含模拟结果</span>
      </div>
      <el-empty v-if="history.length === 0" description="暂无检测状态记录" />
      <ol v-else>
        <li v-for="item in history" :key="item.result_id">
          <el-tag :type="item.label === 'fallen' ? 'danger' : item.label === 'normal' ? 'success' : 'info'" effect="plain">
            {{ item.label }}
          </el-tag>
          <span>{{ formatTime(item.result_timestamp) }}</span>
          <span>Score {{ display(item.score) }}</span>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.fall-notice { margin: -8px 0 18px; padding: 11px 14px; border: 1px solid #eadbbf; border-radius: 9px; color: #755a2c; background: #fffaf0; font-size: 13px; }
.fall-notice--error { border-color: #efd2cf; color: var(--color-danger); background: #fff3f1; }
.fall-alert { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: -8px 0 18px; padding: 16px 20px; border: 1px solid #d93838; border-radius: 10px; color: #fff; background: #bd2525; box-shadow: 0 10px 24px rgba(189, 37, 37, .2); }
.fall-alert div { display: grid; gap: 4px; }
.fall-alert strong { font-size: 20px; }
.fall-alert button { padding: 9px 15px; border: 1px solid rgba(255,255,255,.65); border-radius: 7px; color: #8e1717; background: #fff; font-weight: 700; cursor: pointer; }
.analysis-view { margin-bottom: 20px; }
.analysis-view__actions { display: flex; align-items: center; gap: 10px; }
.preview-reconnect { padding: 7px 12px; border: 1px solid var(--color-border); border-radius: 7px; color: var(--color-heading); background: #fff; cursor: pointer; }
.analysis-canvas { position: relative; display: grid; min-height: 420px; margin-top: 18px; overflow: hidden; place-items: center; border: 1px solid #273a35; border-radius: 10px; background: #0b1110; }
.analysis-canvas--alert { border: 3px solid #d93838; }
.analysis-canvas img { display: block; width: 100%; max-height: 620px; object-fit: contain; }
.analysis-canvas__empty { position: absolute; inset: 0; display: grid; align-content: center; justify-items: center; gap: 8px; color: #d9e6e1; background: #0b1110; }
.analysis-canvas__empty span { color: #91a69e; font-size: 13px; }
.analysis-view__note { margin: 13px 0 0; color: var(--color-text-muted); font-size: 12px; }
.analysis-view__note a { color: var(--color-primary); font-weight: 650; }
.fall-overview-grid { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 20px; margin-bottom: 20px; }
.current-state__value { display: block; margin-top: 32px; color: var(--color-heading); font-size: 38px; letter-spacing: .04em; }
.current-state > p { margin: 10px 0 28px; color: var(--color-text-secondary); }
.current-state > p.current-state__observation { margin-top: -16px; color: #a86d13; font-size: 12px; }
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
.fall-history { margin-top: 20px; }
.fall-history ol { display: grid; gap: 0; margin: 18px 0 0; padding: 0; list-style: none; }
.fall-history li { display: grid; grid-template-columns: 150px 1fr 120px; align-items: center; gap: 14px; padding: 11px 0; border-bottom: 1px solid var(--color-border-light); color: var(--color-text-secondary); font-size: 13px; }
@media (max-width: 1350px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
