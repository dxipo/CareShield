<script setup lang="ts">
import {
  Bell,
  Camera,
  CircleCheck,
  Lock,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import { ApiRequestError, fetchDevices } from '../api/devices'
import { fetchRiskEvents } from '../api/events'
import { fetchFallRiskStatus } from '../api/fallRisk'
import DashboardLiveMonitor from '../components/DashboardLiveMonitor.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusCard from '../components/StatusCard.vue'
import { latestFallDetection, latestFraudDetection } from '../realtime'
import type { AlgorithmCapabilities, AlgorithmResult } from '../realtime/types'

const onlineDeviceValue = ref('--')
const onlineDeviceDescription = ref('正在获取设备')
const initialFallDetection = ref<AlgorithmResult | null>(null)
const initialFraudDetection = ref<AlgorithmResult | null>(null)
const capabilities = ref<AlgorithmCapabilities | null>(null)
const fallRiskReady = ref(false)
const fallRiskModelReady = ref(false)
const riskEvents = ref<AlgorithmResult[]>([])
const now = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const fallResult = computed(() => latestFallDetection.value ?? initialFallDetection.value)
const fraudResult = computed(() => latestFraudDetection.value ?? initialFraudDetection.value)
const fallResultFresh = computed(() => {
  const result = fallResult.value
  return Boolean(
    result &&
      result.task === 'fall_detection' &&
      result.simulated === false &&
      now.value - Date.parse(result.result_timestamp) < 15_000,
  )
})
const fallDetectionValue = computed(() => {
  if (!fallResultFresh.value || !fallResult.value) {
    return capabilities.value?.fall_detection === 'running' ? '运行中' : '不可用'
  }
  return {
    normal: '正常',
    suspected_fall: '疑似跌倒',
    fallen: '检测到跌倒',
    recovering: '恢复中',
    no_person: '未检测到人员',
    low_pose_confidence: '置信度不足',
    warming_up: '初始化中',
    waiting_for_media: '等待视频',
    waiting_for_pose: '等待姿态',
  }[fallResult.value.label] ?? '运行中'
})
const fallDetectionDescription = computed(() => {
  if (!fallResultFresh.value || !fallResult.value) {
    return capabilities.value?.fall_detection === 'running' ? '跌倒监测持续运行' : '检测服务不可用'
  }
  if (fallResult.value.label === 'no_person') return '未检测到人员'
  if (fallResult.value.label === 'low_pose_confidence') return '姿态置信度不足'
  return '跌倒监测正常运行'
})
const fallDetectionTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  if (!fallResultFresh.value || !fallResult.value) {
    return capabilities.value?.fall_detection === 'running' ? 'success' : 'neutral'
  }
  if (fallResult.value.label === 'fallen') return 'danger'
  if (fallResult.value.label === 'suspected_fall' || fallResult.value.label === 'recovering') {
    return 'warning'
  }
  return fallResult.value.label === 'normal' ? 'success' : 'neutral'
})

const fraudValue = computed(() => {
  const result = fraudResult.value
  if (!result || result.simulated || result.task !== 'fraud_detection') {
    return capabilities.value?.fraud_detection === 'running' ? '监听中' : '不可用'
  }
  return {
    normal: '正常',
    suspicious: '可疑话术',
    warning: '疑似诈骗',
    critical: '高风险诈骗',
  }[result.label] ?? '监听中'
})
const fraudTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  if (fraudResult.value?.label === 'critical') return 'danger'
  if (['suspicious', 'warning'].includes(fraudResult.value?.label ?? '')) return 'warning'
  return capabilities.value?.fraud_detection === 'running' ? 'success' : 'neutral'
})
const fraudDescription = computed(() =>
  capabilities.value?.fraud_detection === 'running' ? '音频监测正常运行' : '诈骗检测 Worker 未就绪',
)

const safetyValue = computed(() => {
  if (fraudResult.value?.label === 'critical') return '风险告警'
  if (fraudResult.value?.label === 'warning') return '重点关注'
  if (fallResultFresh.value && fallResult.value?.label === 'fallen') return '风险告警'
  if (fallResultFresh.value && fallResult.value?.label === 'suspected_fall') return '重点关注'
  return capabilities.value?.fall_detection === 'running' ? '监测中' : '不可用'
})
const safetyDescription = computed(() => {
  const running = [
    capabilities.value?.fall_detection,
    capabilities.value?.fraud_detection,
  ].filter((value) => value === 'running').length
  return running > 0 ? `基于 ${running} 项实时安全检测` : '安全监测未运行'
})
const safetyTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  if (safetyValue.value === '风险告警') return 'danger'
  if (safetyValue.value === '重点关注') return 'warning'
  return safetyValue.value === '监测中' ? 'success' : 'neutral'
})
const fallRiskValue = computed(() => (
  fallRiskModelReady.value ? '评估中' : fallRiskReady.value ? '评估就绪' : '暂不可用'
))
const fallRiskDescription = computed(() =>
  fallRiskModelReady.value
    ? '跌倒风险分级与神经运动分析可用'
    : fallRiskReady.value ? '步态评估链路已就绪' : '风险评估 Worker 未就绪',
)

interface RiskTrendPoint {
  key: string
  label: string
  fallCount: number
  fraudCount: number
  total: number
}

function localDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const riskTrend = computed<RiskTrendPoint[]>(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const points = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (6 - index))
    return {
      key: localDateKey(date),
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      fallCount: 0,
      fraudCount: 0,
      total: 0,
    }
  })
  const pointByDay = new Map(points.map((point) => [point.key, point]))

  for (const event of riskEvents.value) {
    const timestamp = new Date(event.result_timestamp)
    if (Number.isNaN(timestamp.getTime())) continue
    const point = pointByDay.get(localDateKey(timestamp))
    if (!point) continue
    if (event.task === 'fall_detection') point.fallCount += 1
    if (event.task === 'fraud_detection') point.fraudCount += 1
    point.total = point.fallCount + point.fraudCount
  }
  return points
})
const riskTrendMax = computed(() => Math.max(1, ...riskTrend.value.map((point) => point.total)))
const riskTrendTotal = computed(() => riskTrend.value.reduce((sum, point) => sum + point.total, 0))
const recentEvents = computed(() => riskEvents.value.slice(0, 3))

function trendBarHeight(total: number): string {
  return total === 0 ? '0%' : `${Math.max(10, (total / riskTrendMax.value) * 100)}%`
}

async function loadOnlineDevices() {
  try {
    const devices = await fetchDevices()
    onlineDeviceValue.value = String(devices.filter((device) => device.online === true).length)
    onlineDeviceDescription.value = `共 ${devices.length} 台设备`
  } catch (error) {
    onlineDeviceValue.value = '--'
    onlineDeviceDescription.value =
      error instanceof ApiRequestError && error.status === 503 ? '设备尚未配置' : '数据获取失败'
  }
}

async function loadFallDetection() {
  try {
    const snapshot = await fetchAlgorithmsStatus()
    capabilities.value = snapshot.capabilities
    const result = snapshot.latest_fall_detection
    if (result?.task === 'fall_detection' && result.simulated === false) {
      initialFallDetection.value = result
    }
    const fraud = snapshot.latest_fraud_detection
    if (fraud?.task === 'fraud_detection' && fraud.simulated === false) {
      initialFraudDetection.value = fraud
    }
  } catch {
    initialFallDetection.value = null
    capabilities.value = null
  }
}

async function loadFallRisk() {
  try {
    const status = await fetchFallRiskStatus()
    fallRiskReady.value = status.ready
    fallRiskModelReady.value = status.kinecal_pipeline.status === 'ready'
  } catch {
    fallRiskReady.value = false
    fallRiskModelReady.value = false
  }
}

async function loadRecentEvents() {
  try {
    riskEvents.value = await fetchRiskEvents(100)
  } catch {
    riskEvents.value = []
  }
}

function formatEventTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

function refreshDashboardState(): void {
  void loadFallDetection()
  void loadFallRisk()
  void loadRecentEvents()
}

onMounted(() => {
  void loadOnlineDevices()
  refreshDashboardState()
  refreshTimer = setInterval(refreshDashboardState, 10_000)
  clockTimer = setInterval(() => (now.value = Date.now()), 1_000)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
  <div class="dashboard-view">
    <PageHeader
      eyebrow="CARE OVERVIEW"
      title="居家安全综合态势"
    />

    <section class="dashboard-status-grid" aria-label="核心状态概览">
      <StatusCard
        title="当前安全状态"
        :value="safetyValue"
        :description="safetyDescription"
        :icon="CircleCheck"
        :tone="safetyTone"
      />
      <StatusCard
        title="跌倒风险"
        :value="fallRiskValue"
        :description="fallRiskDescription"
        :icon="TrendCharts"
        :tone="fallRiskReady ? 'success' : 'neutral'"
      />
      <StatusCard
        title="跌倒检测"
        :value="fallDetectionValue"
        :description="fallDetectionDescription"
        :icon="Warning"
        :tone="fallDetectionTone"
      />
      <StatusCard
        title="诈骗风险"
        :value="fraudValue"
        :description="fraudDescription"
        :icon="Lock"
        :tone="fraudTone"
      />
      <StatusCard
        title="在线设备"
        :value="onlineDeviceValue"
        :description="onlineDeviceDescription"
        :icon="Camera"
        :tone="onlineDeviceValue === '--' ? 'neutral' : 'success'"
      />
    </section>

    <section class="dashboard-primary-grid">
      <article class="panel-card monitor-panel">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">LIVE MONITOR</span>
            <h2>实时监控</h2>
          </div>
          <el-tag effect="dark" type="success">LIVE</el-tag>
        </div>
        <DashboardLiveMonitor />
      </article>

    </section>

    <section class="dashboard-secondary-grid">
      <article class="panel-card">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">RISK TREND</span>
            <h2>风险趋势</h2>
          </div>
          <span class="panel-card__hint">近 7 日 · {{ riskTrendTotal }} 条</span>
        </div>
        <div class="risk-trend" aria-label="近七日真实风险事件趋势">
          <div class="risk-trend__legend">
            <span><i class="risk-trend__dot risk-trend__dot--fall"></i>跌倒事件</span>
            <span><i class="risk-trend__dot risk-trend__dot--fraud"></i>诈骗风险</span>
          </div>
          <div class="risk-trend__plot">
            <div v-for="point in riskTrend" :key="point.key" class="risk-trend__point">
              <span class="risk-trend__value">{{ point.total || '' }}</span>
              <div class="risk-trend__track">
                <div
                  class="risk-trend__bar"
                  :style="{ height: trendBarHeight(point.total) }"
                  :title="`${point.label}：跌倒 ${point.fallCount}，诈骗 ${point.fraudCount}`"
                >
                  <i v-if="point.fallCount" class="risk-trend__segment risk-trend__segment--fall" :style="{ flex: point.fallCount }"></i>
                  <i v-if="point.fraudCount" class="risk-trend__segment risk-trend__segment--fraud" :style="{ flex: point.fraudCount }"></i>
                </div>
              </div>
              <time :datetime="point.key">{{ point.label }}</time>
            </div>
            <span v-if="riskTrendTotal === 0" class="risk-trend__empty">近 7 日暂无风险事件</span>
          </div>
        </div>
      </article>

      <article class="panel-card">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">RECENT EVENTS</span>
            <h2>最近风险事件</h2>
          </div>
        </div>
        <EmptyState
          v-if="recentEvents.length === 0"
          compact
          title="暂无风险事件"
          description="新的真实跌倒事件会自动记录。"
          :icon="Bell"
        />
        <ol v-else class="dashboard-events">
          <li v-for="event in recentEvents" :key="event.result_id">
            <span><i></i><strong>{{ event.task === 'fraud_detection' ? '疑似诈骗告警' : '检测到跌倒' }}</strong></span>
            <time :datetime="event.result_timestamp">{{ formatEventTime(event.result_timestamp) }}</time>
          </li>
          <li class="dashboard-events__more"><router-link to="/events">查看全部风险事件</router-link></li>
        </ol>
      </article>
    </section>
  </div>
</template>

<style scoped>
.dashboard-status-grid {
  display: grid;
  margin-bottom: 20px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}

.monitor-panel {
  border-color: var(--color-card-emphasis-border);
  box-shadow: var(--shadow-card-emphasis);
}

.dashboard-primary-grid,
.dashboard-secondary-grid {
  display: grid;
  margin-bottom: 20px;
  gap: 20px;
}

.dashboard-events {
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.dashboard-events li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-secondary);
  font-size: 12px;
}

.dashboard-events span {
  display: flex;
  align-items: center;
  gap: 9px;
}

.dashboard-events i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-danger);
}

.dashboard-events strong {
  color: var(--color-heading);
}

.dashboard-events time {
  font-size: 11px;
}

.dashboard-events li.dashboard-events__more {
  justify-content: flex-end;
  border-bottom: 0;
}

.dashboard-events a {
  color: var(--color-primary);
  font-weight: 650;
  text-decoration: none;
}

.dashboard-primary-grid {
  grid-template-columns: minmax(0, 1fr);
}

.dashboard-secondary-grid {
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.75fr);
}

.risk-trend {
  margin-top: 18px;
}

.risk-trend__legend {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  color: var(--color-text-secondary);
  font-size: 11px;
}

.risk-trend__legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.risk-trend__dot {
  width: 8px;
  height: 8px;
  border-radius: 3px;
}

.risk-trend__dot--fall,
.risk-trend__segment--fall {
  background: var(--color-danger);
}

.risk-trend__dot--fraud,
.risk-trend__segment--fraud {
  background: var(--color-warning);
}

.risk-trend__plot {
  position: relative;
  display: grid;
  height: 190px;
  margin-top: 14px;
  padding: 8px 8px 0;
  border-top: 1px solid var(--color-border-light);
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent 44px,
    var(--color-border-light) 45px
  );
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px;
}

.risk-trend__point {
  display: grid;
  min-width: 0;
  grid-template-rows: 18px 1fr 25px;
  text-align: center;
}

.risk-trend__value {
  color: var(--color-text-secondary);
  font-size: 11px;
  font-weight: 650;
}

.risk-trend__track {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  min-height: 0;
}

.risk-trend__bar {
  display: flex;
  width: min(30px, 64%);
  min-height: 0;
  overflow: hidden;
  border-radius: 6px 6px 2px 2px;
  flex-direction: column-reverse;
}

.risk-trend__segment {
  display: block;
  min-height: 4px;
}

.risk-trend__point time {
  padding-top: 8px;
  color: var(--color-text-muted);
  font-size: 11px;
}

.risk-trend__empty {
  position: absolute;
  top: 76px;
  right: 0;
  left: 0;
  color: var(--color-text-muted);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 1450px) {
  .dashboard-status-grid {
    gap: 12px;
  }

  .dashboard-primary-grid,
  .dashboard-secondary-grid {
    gap: 16px;
  }
}
</style>
