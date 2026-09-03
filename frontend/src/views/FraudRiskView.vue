<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  acknowledgeFraudAlert,
  fetchAlgorithmsStatus,
  fetchFraudDetectionHistory,
} from '../api/algorithms'
import PageHeader from '../components/PageHeader.vue'
import { latestFraudDetection, realtimeStatus } from '../realtime'
import type { AlgorithmResult, WorkerStatus } from '../realtime/types'

const initialResult = ref<AlgorithmResult | null>(null)
const worker = ref<WorkerStatus | null>(null)
const loadError = ref(false)
const history = ref<AlgorithmResult[]>([])
const historyPage = ref(1)
const acknowledging = ref(false)
const alertSuppressed = ref(false)
let refresh: ReturnType<typeof setInterval> | null = null

const MINIMUM_DISPLAY_CONFIDENCE = 0.5
const HISTORY_PAGE_SIZE = 5
const result = computed(() => {
  const realtime = latestFraudDetection.value
  if (isDisplayableResult(realtime)) return realtime
  return isDisplayableResult(initialResult.value) ? initialResult.value : null
})
const available = computed(
  () => worker.value?.online === true && worker.value.capabilities.fraud_detection === 'running',
)
const currentState = computed(() => {
  if (result.value?.task === 'fraud_detection' && result.value.simulated === false) {
    return result.value.label
  }
  return available.value ? 'listening' : 'unavailable'
})
const stateText = computed(() => fraudStateText(currentState.value))
const stateType = computed(() => {
  if (currentState.value === 'critical') return 'danger'
  if (currentState.value === 'warning' || currentState.value === 'suspicious') return 'warning'
  if (currentState.value === 'normal' || currentState.value === 'listening') return 'success'
  return 'info'
})
const metadata = computed<Record<string, unknown>>(() => result.value?.metadata ?? {})
const runtime = computed<Record<string, unknown>>(() => {
  const value = worker.value?.runtime?.fraud_detection
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
})
const categories = computed(() => arrayOfStrings(metadata.value.evidence_categories))
const alertSignal = computed(() => {
  if (runtime.value.alert_acknowledged === true) return false
  return metadata.value.alert_active === true || runtime.value.alert_active === true
})
const alertActive = computed(() =>
  alertSignal.value && !alertSuppressed.value && ['warning', 'critical'].includes(currentState.value),
)
const fraudHistory = computed(() =>
  history.value.filter((item) => item.task === 'fraud_detection' && item.simulated === false),
)
const historyPageCount = computed(() =>
  Math.max(1, Math.ceil(fraudHistory.value.length / HISTORY_PAGE_SIZE)),
)
const paginatedHistory = computed(() => {
  const start = (historyPage.value - 1) * HISTORY_PAGE_SIZE
  return fraudHistory.value.slice(start, start + HISTORY_PAGE_SIZE)
})

watch(alertSignal, (active) => {
  // A normal detector state rearms the UI for the next independent incident.
  if (!active) alertSuppressed.value = false
})

function fraudStateText(state: string): string {
  return ({
    normal: '正常',
    listening: '监听中',
    suspicious: '发现可疑话术',
    warning: '疑似诈骗',
    critical: '高风险诈骗',
    unavailable: '检测不可用',
  }[state] ?? state)
}

function historyTone(label: string): 'success' | 'warning' | 'danger' | 'info' {
  if (label === 'critical') return 'danger'
  if (label === 'warning' || label === 'suspicious') return 'warning'
  if (label === 'normal') return 'success'
  return 'info'
}

function historyMetadata(item: AlgorithmResult): Record<string, unknown> {
  return item.metadata ?? {}
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function isDisplayableResult(value: AlgorithmResult | null): value is AlgorithmResult {
  if (value?.task !== 'fraud_detection' || value.simulated !== false) return false
  const confidence = value.metadata?.asr_confidence
  return typeof confidence !== 'number' || confidence >= MINIMUM_DISPLAY_CONFIDENCE
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

async function acknowledgeAlert(): Promise<void> {
  acknowledging.value = true
  try {
    await acknowledgeFraudAlert()
    alertSuppressed.value = true
    await loadStatus()
  } finally {
    acknowledging.value = false
  }
}

async function loadStatus(): Promise<void> {
  try {
    const [snapshot, records] = await Promise.all([
      fetchAlgorithmsStatus(),
      fetchFraudDetectionHistory(100),
    ])
    worker.value = snapshot.workers.find(
      (item) => item.capabilities.fraud_detection !== 'not_installed',
    ) ?? null
    if (isDisplayableResult(snapshot.latest_fraud_detection)) {
      initialResult.value = snapshot.latest_fraud_detection
    }
    history.value = records
    historyPage.value = Math.min(historyPage.value, historyPageCount.value)
    loadError.value = false
  } catch {
    loadError.value = true
  }
}

onMounted(() => {
  void loadStatus()
  refresh = setInterval(loadStatus, 10_000)
})

onBeforeUnmount(() => {
  if (refresh) clearInterval(refresh)
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="REAL-TIME FRAUD RISK"
      title="诈骗风险监测"
    />

    <section v-if="alertActive" class="fraud-alert" role="alert">
      <div>
        <strong>{{ currentState === 'critical' ? '检测到高风险诈骗话术' : '检测到疑似诈骗话术' }}</strong>
        <span>请立即停止转账，不要提供验证码、银行卡号或身份证信息，并联系家属核实。</span>
      </div>
      <button type="button" :disabled="acknowledging" @click="acknowledgeAlert">
        {{ acknowledging ? '正在确认...' : '确认已处理' }}
      </button>
    </section>

    <p v-if="loadError" class="fraud-notice fraud-notice--error">诈骗检测状态暂时无法获取。</p>

    <section class="fraud-grid">
      <article class="panel-card risk-state" :class="`risk-state--${stateType}`">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">CURRENT RISK</span><h2>当前风险</h2></div>
          <el-tag :type="stateType" effect="dark">{{ stateText }}</el-tag>
        </div>
        <strong>{{ stateText }}</strong>
        <p>{{ available ? '音频监测与风险分析正常运行' : 'Fraud Worker 或音频输入当前不可用' }}</p>
        <dl>
          <div><dt>Evidence Score</dt><dd>{{ result?.score == null ? '--' : result.score.toFixed(3) }}</dd></div>
          <div><dt>Level</dt><dd>{{ result?.level?.toUpperCase() ?? '--' }}</dd></div>
          <div><dt>Last Result</dt><dd>{{ formatTime(result?.result_timestamp) }}</dd></div>
          <div><dt>Realtime</dt><dd>{{ realtimeStatus }}</dd></div>
        </dl>
      </article>

      <article class="panel-card transcript-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">VOICE RISK ANALYSIS</span><h2>语音风险分析</h2></div>
          <el-tag effect="plain">内容已脱敏</el-tag>
        </div>
        <blockquote v-if="metadata.transcript_preview">{{ metadata.transcript_preview }}</blockquote>
        <div v-else class="transcript-empty">等待检测到有效语音...</div>
        <div class="evidence-list">
          <span v-if="categories.length === 0">暂无风险证据</span>
          <el-tag v-for="category in categories" :key="category" type="warning" effect="plain">
            {{ category }}
          </el-tag>
        </div>
        <dl class="transcript-metrics">
          <div><dt>Utterance</dt><dd>{{ display(metadata.utterance_seconds, ' s') }}</dd></div>
          <div><dt>ASR Latency</dt><dd>{{ display(metadata.asr_latency_ms, ' ms') }}</dd></div>
          <div><dt>AI Latency</dt><dd>{{ result?.latency_ms == null ? '--' : `${result.latency_ms.toFixed(0)} ms` }}</dd></div>
          <div><dt>LLM Used</dt><dd>{{ display(metadata.llm_used) }}</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel-card fraud-history">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">DETECTION HISTORY</span><h2>检测记录</h2></div>
        <el-tag effect="plain">共 {{ fraudHistory.length }} 条</el-tag>
      </div>
      <el-empty v-if="fraudHistory.length === 0" description="暂无诈骗检测记录" />
      <template v-else>
        <ol>
          <li v-for="item in paginatedHistory" :key="item.result_id">
            <span class="history-status" :class="`history-status--${historyTone(item.label)}`">
              {{ fraudStateText(item.label) }}
            </span>
            <span class="history-transcript">
              {{ historyMetadata(item).transcript_preview || '未记录有效文本摘要' }}
            </span>
            <span>Evidence {{ item.score == null ? '--' : item.score.toFixed(3) }}</span>
            <time :datetime="item.result_timestamp">{{ formatTime(item.result_timestamp) }}</time>
          </li>
        </ol>
        <div class="history-pagination-row">
          <span>第 {{ historyPage }} / {{ historyPageCount }} 页</span>
          <el-pagination
            v-model:current-page="historyPage"
            class="history-pagination"
            background
            layout="prev, pager, next, jumper"
            :page-size="HISTORY_PAGE_SIZE"
            :pager-count="5"
            :total="fraudHistory.length"
          />
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.fraud-alert { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 16px; padding: 16px 18px; border: 1px solid #d93838; border-radius: 10px; color: #fff; background: #bd2525; box-shadow: 0 10px 24px rgba(189, 37, 37, .2); }
.fraud-alert div { display: grid; gap: 4px; }
.fraud-alert strong, .fraud-alert span { display: block; }
.fraud-alert strong { font-size: 18px; }
.fraud-alert span { font-size: 13px; }
.fraud-alert button { flex: 0 0 auto; padding: 9px 15px; border: 1px solid rgba(255,255,255,.65); border-radius: 7px; color: #8e1717; background: #fff; font-weight: 700; cursor: pointer; }
.fraud-alert button:disabled { cursor: wait; opacity: .7; }
.fraud-notice { margin: -6px 0 18px; color: var(--color-text-muted); font-size: 12px; }
.fraud-notice--error { color: var(--color-danger); }
.fraud-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.risk-state > strong { display: block; margin: 24px 0 8px; color: var(--color-heading); font-size: 34px; }
.risk-state > p { color: var(--color-text-muted); font-size: 12px; }
.risk-state--danger { border-color: var(--color-danger-border); }
dl { margin: 22px 0 0; }
dl div { display: flex; justify-content: space-between; padding: 11px 0; border-bottom: 1px solid var(--color-border-light); }
dt { color: var(--color-text-muted); font-size: 12px; }
dd { margin: 0; color: var(--color-heading); font-size: 12px; font-weight: 650; }
.transcript-card { min-width: 0; }
.transcript-card blockquote { min-height: 86px; margin: 22px 0; padding: 18px; border-left: 3px solid var(--color-primary); color: var(--color-heading); background: var(--color-surface-soft); font-size: 16px; line-height: 1.8; }
.transcript-empty { margin: 22px 0; padding: 30px; color: var(--color-text-muted); background: var(--color-surface-soft); text-align: center; }
.evidence-list { display: flex; align-items: center; min-height: 32px; gap: 8px; color: var(--color-text-muted); font-size: 12px; }
.transcript-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.transcript-metrics div { display: block; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 8px; }
.transcript-metrics dd { margin-top: 8px; }
.fraud-history { margin-top: 20px; }
.fraud-history ol { display: grid; margin: 18px 0 0; padding: 0; list-style: none; }
.fraud-history li { display: grid; align-items: center; padding: 12px 0; grid-template-columns: 130px minmax(220px, 1fr) 130px 180px; gap: 14px; border-bottom: 1px solid var(--color-border-light); color: var(--color-text-secondary); font-size: 12px; }
.history-status { display: inline-flex; align-items: center; justify-content: center; width: fit-content; min-width: 64px; padding: 5px 10px; border: 1px solid var(--color-border); border-radius: 999px; color: var(--color-text-secondary); background: var(--color-surface-soft); font-weight: 650; }
.history-status--success { border-color: var(--color-success-border); color: var(--color-success); background: var(--color-success-soft); }
.history-status--warning { border-color: var(--color-warning-border); color: var(--color-warning-text); background: var(--color-warning-soft); }
.history-status--danger { border-color: var(--color-danger-border); color: var(--color-danger-text); background: var(--color-danger-soft); }
.history-transcript { overflow: hidden; color: var(--color-heading); text-overflow: ellipsis; white-space: nowrap; }
.fraud-history time { text-align: right; }
.history-pagination-row { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-top: 10px; color: var(--color-text-secondary); font-size: 12px; }
.history-pagination { justify-content: flex-end; }
.history-pagination :deep(.btn-prev), .history-pagination :deep(.btn-next), .history-pagination :deep(.el-pager li) { border: 1px solid var(--color-border); background: var(--color-control-bg) !important; }
.history-pagination :deep(.el-pager li.is-active) { border-color: var(--color-primary); color: #fff; background: var(--color-primary) !important; }
@media (max-width: 1366px) { .fraud-grid { gap: 14px; } .transcript-metrics { gap: 8px; } }
</style>
