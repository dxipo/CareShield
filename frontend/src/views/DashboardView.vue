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
import { onMounted, ref } from 'vue'

import { ApiRequestError, fetchDevices } from '../api/devices'
import BackendStatusPanel from '../components/BackendStatusPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusCard from '../components/StatusCard.vue'

const onlineDeviceValue = ref('--')
const onlineDeviceDescription = ref('正在获取设备')

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

onMounted(loadOnlineDevices)
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
      <StatusCard title="跌倒检测" value="--" description="暂无数据" :icon="Warning" />
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
