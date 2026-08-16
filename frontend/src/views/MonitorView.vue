<script setup lang="ts">
import { VideoCamera } from '@element-plus/icons-vue'

import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'

const connectionStates = [
  { label: '设备来源', value: '未接入' },
  { label: '视频通道', value: '未接入' },
  { label: '音频通道', value: '未接入' },
]
</script>

<template>
  <div>
    <PageHeader
      eyebrow="LIVE MONITOR"
      title="实时监测"
      description="用于未来查看摄像设备实时画面与连接状态。M2 仅查询设备信息，不接入视频或测试视频。"
    />

    <section class="monitor-layout">
      <article class="panel-card monitor-workspace">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">CAMERA VIEW</span>
            <h2>监控画面</h2>
          </div>
          <el-tag effect="plain" type="info">No signal</el-tag>
        </div>
        <div class="monitor-workspace__viewport">
          <EmptyState
            title="摄像头尚未接入"
            description="萤石设备与视频流将在后续独立 Adapter 阶段接入。"
            :icon="VideoCamera"
          />
        </div>
      </article>

      <aside class="panel-card connection-panel">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">CONNECTION</span>
            <h2>接入状态</h2>
          </div>
        </div>
        <dl>
          <div v-for="item in connectionStates" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
        <p>当前不读取摄像头、音频或设备事件。</p>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.monitor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 20px;
}

.monitor-workspace__viewport {
  min-height: 520px;
  margin-top: 18px;
  border: 1px solid #dce6e2;
  border-radius: 11px;
  background:
    linear-gradient(135deg, rgb(74 126 108 / 3%) 25%, transparent 25%) -16px 0 / 32px 32px,
    linear-gradient(225deg, rgb(74 126 108 / 3%) 25%, transparent 25%) -16px 0 / 32px 32px,
    #f5f8f7;
}

.monitor-workspace__viewport :deep(.empty-state) {
  min-height: 520px;
}

.connection-panel {
  align-self: start;
}

dl {
  margin: 18px 0 0;
}

dl div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 0;
  border-bottom: 1px solid var(--color-border-light);
}

dt {
  color: var(--color-text-secondary);
  font-size: 13px;
}

dd {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.connection-panel > p {
  margin: 18px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.7;
}
</style>
