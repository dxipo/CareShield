<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import PageHeader from '../components/PageHeader.vue'
import { latestFraudDetection, realtimeStatus } from '../realtime'
import type { AlgorithmResult, WorkerStatus } from '../realtime/types'

const initialResult = ref<AlgorithmResult | null>(null)
const worker = ref<WorkerStatus | null>(null)
const loadError = ref(false)
let refresh: ReturnType<typeof setInterval> | null = null

const MINIMUM_DISPLAY_CONFIDENCE = 0.5
const result = computed(() => {
  const realtime = latestFraudDetection.value
  if (isDisplayableResult(realtime)) return realtime
  return isDisplayableResult(initialResult.value) ? initialResult.value : null
})
const runtime = computed<Record<string, unknown>>(() => {
  const value = worker.value?.runtime?.fraud_detection
  return isRecord(value) ? value : {}
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
const stateText = computed(() => ({
  normal: '正常',
  listening: '监听中',
  suspicious: '发现可疑话术',
  warning: '疑似诈骗',
  critical: '高风险诈骗',
  unavailable: '检测不可用',
}[currentState.value] ?? currentState.value))
const stateType = computed(() => {
  if (currentState.value === 'critical') return 'danger'
  if (currentState.value === 'warning' || currentState.value === 'suspicious') return 'warning'
  if (currentState.value === 'normal' || currentState.value === 'listening') return 'success'
  return 'info'
})
const metadata = computed<Record<string, unknown>>(() => result.value?.metadata ?? {})
const categories = computed(() => arrayOfStrings(metadata.value.evidence_categories))
const alertActive = computed(
  () => metadata.value.alert_active === true && ['warning', 'critical'].includes(currentState.value),
)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

async function loadStatus(): Promise<void> {
  try {
    const snapshot = await fetchAlgorithmsStatus()
    worker.value = snapshot.workers.find(
      (item) => item.capabilities.fraud_detection !== 'not_installed',
    ) ?? null
    if (isDisplayableResult(snapshot.latest_fraud_detection)) {
      initialResult.value = snapshot.latest_fraud_detection
    }
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
      description="从真实 H6c 音频提取语音文本，经本地规则证据与可选 Ollama 复核后实时提示风险。"
    />

    <section v-if="alertActive" class="fraud-alert" role="alert">
      <strong>{{ currentState === 'critical' ? '检测到高风险诈骗话术' : '检测到疑似诈骗话术' }}</strong>
      <span>请立即停止转账，不要提供验证码、银行卡号或身份证信息，并联系家属核实。</span>
    </section>

    <p v-if="loadError" class="fraud-notice fraud-notice--error">诈骗检测状态暂时无法获取。</p>
    <p class="fraud-notice">
      当前分数表示规则、上下文与模型证据强度，不是经过统计校准的诈骗概率；完整音频不保存，页面文本已限制长度并脱敏。
    </p>

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

      <article class="panel-card runtime-card">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">RUNTIME</span><h2>音频与模型</h2></div>
          <el-tag :type="available ? 'success' : 'info'" effect="plain">
            {{ available ? 'Worker Online' : 'Worker Unavailable' }}
          </el-tag>
        </div>
        <dl>
          <div><dt>Audio</dt><dd>{{ display(runtime.audio_status) }}</dd></div>
          <div><dt>ASR</dt><dd>{{ display(runtime.asr_provider) }} / {{ display(runtime.asr_status) }}</dd></div>
          <div><dt>ASR Device</dt><dd>{{ display(runtime.asr_device) }}</dd></div>
          <div><dt>LLM</dt><dd>{{ display(runtime.llm_model) }}</dd></div>
          <div><dt>LLM Ready</dt><dd>{{ display(runtime.llm_ready) }}</dd></div>
          <div><dt>Processed</dt><dd>{{ display(runtime.processed_utterances) }}</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel-card transcript-card">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">PRIVACY-SAFE TRANSCRIPT</span><h2>最近语音与风险证据</h2></div>
        <el-tag effect="plain">仅脱敏摘要</el-tag>
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
    </section>
  </div>
</template>

<style scoped>
.fraud-alert { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; padding: 16px 18px; border: 1px solid var(--color-danger-border); border-radius: 10px; color: var(--color-danger-text); background: var(--color-danger-soft); }
.fraud-alert strong, .fraud-alert span { display: block; }
.fraud-alert span { margin-left: 18px; font-size: 13px; }
.fraud-notice { margin: -6px 0 18px; color: var(--color-text-muted); font-size: 12px; }
.fraud-notice--error { color: var(--color-danger); }
.fraud-grid { display: grid; margin-bottom: 20px; grid-template-columns: 1.15fr 0.85fr; gap: 20px; }
.risk-state > strong { display: block; margin: 24px 0 8px; color: var(--color-heading); font-size: 34px; }
.risk-state > p { color: var(--color-text-muted); font-size: 12px; }
.risk-state--danger { border-color: var(--color-danger-border); }
dl { margin: 22px 0 0; }
dl div { display: flex; justify-content: space-between; padding: 11px 0; border-bottom: 1px solid var(--color-border-light); }
dt { color: var(--color-text-muted); font-size: 12px; }
dd { margin: 0; color: var(--color-heading); font-size: 12px; font-weight: 650; }
.transcript-card blockquote { margin: 22px 0; padding: 18px; border-left: 3px solid var(--color-primary); color: var(--color-heading); background: var(--color-surface-soft); font-size: 16px; line-height: 1.8; }
.transcript-empty { margin: 22px 0; padding: 30px; color: var(--color-text-muted); background: var(--color-surface-soft); text-align: center; }
.evidence-list { display: flex; align-items: center; min-height: 32px; gap: 8px; color: var(--color-text-muted); font-size: 12px; }
.transcript-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.transcript-metrics div { display: block; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 8px; }
.transcript-metrics dd { margin-top: 8px; }
@media (max-width: 1366px) { .fraud-grid { gap: 14px; } }
</style>
