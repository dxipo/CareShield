<script setup lang="ts">
import {
  Bell,
  Camera,
  CircleCheck,
  DataLine,
  Lock,
  TrendCharts,
  VideoCamera,
  Warning,
} from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import { ApiRequestError, fetchDevices } from '../api/devices'
import BackendStatusPanel from '../components/BackendStatusPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusCard from '../components/StatusCard.vue'
import { latestFallDetection } from '../realtime'
import type { AlgorithmResult } from '../realtime/types'

const onlineDeviceValue = ref('--')
const onlineDeviceDescription = ref('正在获取设备')
const initialFallDetection = ref<AlgorithmResult | null>(null)
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
  if (!fallResultFresh.value || !fallResult.value) return '--'
  return {
    normal: '正常',
    suspected_fall: '疑似跌倒',
    fallen: '检测到跌倒',
    recovering: '恢复中',
    no_person: '--',
    low_pose_confidence: '--',
  }[fallResult.value.label] ?? '--'
})
const fallDetectionDescription = computed(() => {
  if (!fallResultFresh.value || !fallResult.value) return '检测服务不可用'
  if (fallResult.value.label === 'no_person') return '未检测到人员'
  if (fallResult.value.label === 'low_pose_confidence') return '姿态置信度不足'
  return '真实实时检测'
})
const fallDetectionTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  if (!fallResultFresh.value || !fallResult.value) return 'neutral'
  if (fallResult.value.label === 'fallen') return 'danger'
  if (fallResult.value.label === 'suspected_fall' || fallResult.value.label === 'recovering') {
    return 'warning'
  }
  return fallResult.value.label === 'normal' ? 'success' : 'neutral'
})

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
    const result = snapshot.latest_fall_detection
    if (result?.task === 'fall_detection' && result.simulated === false) {
      initialFallDetection.value = result
    }
  } catch {
    initialFallDetection.value = null
  }
}

onMounted(() => {
  void loadOnlineDevices()
  void loadFallDetection()
  refreshTimer = setInterval(loadFallDetection, 10_000)
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
      description="统一汇聚设备、风险识别与事件信息。当前仅展示平台基础状态，业务能力将在后续阶段接入。"
    />

    <section class="dashboard-status-grid" aria-label="核心状态概览">
      <StatusCard
        title="当前安全状态"
        value="--"
        description="安全评估未接入"
        :icon="CircleCheck"
      />
      <StatusCard title="跌倒风险" value="--" description="模型未接入" :icon="TrendCharts" />
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
          <el-tag effect="plain" type="info">Not connected</el-tag>
        </div>
        <div class="monitor-panel__viewport">
          <EmptyState
            title="摄像头尚未接入"
            description="当前不播放测试视频，也不使用网络公开视频。"
            :icon="VideoCamera"
          />
        </div>
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
          compact
          title="暂无风险事件"
          description="事件业务尚未接入。"
          :icon="Bell"
        />
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

.dashboard-primary-grid {
  grid-template-columns: minmax(0, 1.9fr) minmax(300px, 0.9fr);
}

.dashboard-secondary-grid {
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.75fr);
}

.monitor-panel__viewport {
  min-height: 326px;
  margin-top: 18px;
  border: 1px solid #dce6e2;
  border-radius: 11px;
  background:
    linear-gradient(rgb(20 43 39 / 2%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(20 43 39 / 2%) 1px, transparent 1px), #f5f8f7;
  background-size: 32px 32px;
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
