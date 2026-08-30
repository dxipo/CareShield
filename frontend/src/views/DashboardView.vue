<script setup lang="ts">
import {
  Bell,
  Camera,
  CircleCheck,
  DataLine,
  Lock,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import { ApiRequestError, fetchDevices } from '../api/devices'
import { fetchRiskEvents } from '../api/events'
import { fetchFallRiskStatus } from '../api/fallRisk'
import BackendStatusPanel from '../components/BackendStatusPanel.vue'
import DashboardLiveMonitor from '../components/DashboardLiveMonitor.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusCard from '../components/StatusCard.vue'
import { latestFallDetection } from '../realtime'
import type { AlgorithmCapabilities, AlgorithmResult } from '../realtime/types'

const onlineDeviceValue = ref('--')
const onlineDeviceDescription = ref('正在获取设备')
const initialFallDetection = ref<AlgorithmResult | null>(null)
const capabilities = ref<AlgorithmCapabilities | null>(null)
const fallRiskReady = ref(false)
const fallRiskModelReady = ref(false)
const recentEvents = ref<AlgorithmResult[]>([])
const now = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const fallResult = computed(() => latestFallDetection.value ?? initialFallDetection.value)
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
    return capabilities.value?.fall_detection === 'running' ? '真实模型持续运行' : '检测服务不可用'
  }
  if (fallResult.value.label === 'no_person') return '未检测到人员'
  if (fallResult.value.label === 'low_pose_confidence') return '姿态置信度不足'
  return '真实实时检测'
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

const safetyValue = computed(() => {
  if (fallResultFresh.value && fallResult.value?.label === 'fallen') return '风险告警'
  if (fallResultFresh.value && fallResult.value?.label === 'suspected_fall') return '重点关注'
  return capabilities.value?.fall_detection === 'running' ? '监测中' : '不可用'
})
const safetyDescription = computed(() =>
  capabilities.value?.fall_detection === 'running' ? '基于实时跌倒检测' : '安全监测未运行',
)
const safetyTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  if (safetyValue.value === '风险告警') return 'danger'
  if (safetyValue.value === '重点关注') return 'warning'
  return safetyValue.value === '监测中' ? 'success' : 'neutral'
})
const fallRiskValue = computed(() => (
  fallRiskModelReady.value ? '核心模型已接入' : fallRiskReady.value ? '特征评估就绪' : '暂不可用'
))
const fallRiskDescription = computed(() =>
  fallRiskModelReady.value
    ? 'MotionCLIP 研究模型可用'
    : fallRiskReady.value ? '步态与 SMPL-X 链路已接入' : '风险评估 Worker 未就绪',
)

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
  } catch {
    initialFallDetection.value = null
    capabilities.value = null
  }
}

async function loadFallRisk() {
  try {
    const status = await fetchFallRiskStatus()
    fallRiskReady.value = status.ready
    fallRiskModelReady.value = status.risk_pipeline.status === 'ready'
  } catch {
    fallRiskReady.value = false
    fallRiskModelReady.value = false
  }
}

async function loadRecentEvents() {
  try {
    recentEvents.value = await fetchRiskEvents(3)
  } catch {
    recentEvents.value = []
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
      description="统一汇聚真实设备、已接入算法能力、实时监测与风险事件；未接入能力保持明确标识。"
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
      <StatusCard title="诈骗风险" value="--" description="模型未接入" :icon="Lock" />
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
          <el-tag effect="plain" type="success">EZOPEN</el-tag>
        </div>
        <DashboardLiveMonitor />
      </article>

      <BackendStatusPanel />
    </section>

    <section class="dashboard-secondary-grid">
      <article class="panel-card">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">RISK TREND</span>
            <h2>风险趋势</h2>
          </div>
          <span class="panel-card__hint">等待真实数据源</span>
        </div>
        <EmptyState
          compact
          title="暂无风险历史数据"
          description="接入真实风险数据后再启用趋势图表。"
          :icon="DataLine"
        />
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
            <span><i></i><strong>检测到跌倒</strong></span>
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
  grid-template-columns: minmax(0, 1.9fr) minmax(300px, 0.9fr);
}

.dashboard-secondary-grid {
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.75fr);
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
