<script setup lang="ts">
import { Bell, Lock, Refresh, Warning } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { fetchRiskEvents } from '../api/events'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import type { AlgorithmResult } from '../realtime/types'

const events = ref<AlgorithmResult[]>([])
const loading = ref(true)
const loadError = ref(false)
const eventPage = ref(1)
const EVENT_PAGE_SIZE = 10

const todayCount = computed(() => {
  const today = new Date().toDateString()
  return events.value.filter((event) => new Date(event.result_timestamp).toDateString() === today).length
})
const latestTime = computed(() => events.value[0]?.result_timestamp ?? null)
const fallCount = computed(() => events.value.filter((event) => event.task === 'fall_detection').length)
const fraudCount = computed(() => events.value.filter((event) => event.task === 'fraud_detection').length)
const eventPageCount = computed(() => Math.max(1, Math.ceil(events.value.length / EVENT_PAGE_SIZE)))
const paginatedEvents = computed(() => {
  const start = (eventPage.value - 1) * EVENT_PAGE_SIZE
  return events.value.slice(start, start + EVENT_PAGE_SIZE)
})

function eventTitle(event: AlgorithmResult): string {
  return event.task === 'fraud_detection' ? '疑似诈骗告警' : '检测到跌倒'
}

function formatTime(value: string | null): string {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function formatScore(score: number | null): string {
  return score === null ? 'Unavailable' : score.toFixed(3)
}

function maskedDevice(deviceId: string | null): string {
  if (!deviceId) return '未关联设备'
  if (deviceId.length <= 4) return '设备 ••••'
  return `设备 ••••${deviceId.slice(-4)}`
}

async function loadEvents(): Promise<void> {
  loading.value = true
  try {
    events.value = (await fetchRiskEvents(100)).filter((event) => event.simulated === false)
    eventPage.value = Math.min(eventPage.value, eventPageCount.value)
    loadError.value = false
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadEvents())
</script>

<template>
  <div>
    <PageHeader
      eyebrow="RISK EVENT CENTER"
      title="风险事件"
    >
      <template #actions>
        <el-button :icon="Refresh" :loading="loading" @click="loadEvents">刷新事件</el-button>
      </template>
    </PageHeader>

    <section class="event-summary" aria-label="风险事件概览">
      <article><span>已记录事件</span><strong>{{ events.length }}</strong><small>仅真实风险结果</small></article>
      <article><span>今日事件</span><strong>{{ todayCount }}</strong><small>按本地日期统计</small></article>
      <article class="event-summary__critical"><span>风险类型</span><strong>{{ fallCount }} / {{ fraudCount }}</strong><small>跌倒 / 诈骗</small></article>
      <article><span>最近发生</span><strong class="event-summary__time">{{ formatTime(latestTime) }}</strong><small>真实检测时间</small></article>
    </section>

    <section class="panel-card event-list">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">RECORDED EVENTS</span><h2>安全风险记录</h2></div>
        <el-tag effect="plain" type="danger">Real results only</el-tag>
      </div>

      <p v-if="loadError" class="event-error">风险事件暂时无法读取，请稍后重试。</p>
      <EmptyState
        v-else-if="!loading && events.length === 0"
        title="暂无已保存的风险事件"
        description="新的真实跌倒或诈骗风险会自动记录在这里；不会补造已经丢失的历史记录。"
        :icon="Bell"
      />
      <div v-else-if="loading" class="event-loading">正在读取风险事件...</div>
      <template v-else>
      <ol>
        <li v-for="event in paginatedEvents" :key="event.result_id">
          <span class="event-list__icon">
            <el-icon :size="21">
              <Lock v-if="event.task === 'fraud_detection'" />
              <Warning v-else />
            </el-icon>
          </span>
          <div class="event-list__primary">
            <div><strong>{{ eventTitle(event) }}</strong><el-tag size="small" type="danger" effect="dark">{{ event.level?.toUpperCase() ?? 'RISK' }}</el-tag></div>
            <p>{{ maskedDevice(event.device_id) }} · {{ event.model_id }} / {{ event.model_version }}</p>
          </div>
          <div class="event-list__metric">
            <span>{{ event.task === 'fraud_detection' ? 'Evidence Score' : 'Fall Score' }}</span>
            <strong>{{ formatScore(event.score) }}</strong>
            <small>未校准模型分数</small>
          </div>
          <time :datetime="event.result_timestamp">{{ formatTime(event.result_timestamp) }}</time>
        </li>
      </ol>
      <div class="event-pagination-row">
        <span>第 {{ eventPage }} / {{ eventPageCount }} 页</span>
        <el-pagination
          v-model:current-page="eventPage"
          class="event-pagination"
          background
          layout="prev, pager, next, jumper"
          :page-size="EVENT_PAGE_SIZE"
          :pager-count="5"
          :total="events.length"
        />
      </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.event-summary {
  display: grid;
  margin-bottom: 20px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.event-summary article {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.event-summary span,
.event-summary small {
  display: block;
  color: var(--color-text-muted);
  font-size: 11px;
}

.event-summary strong {
  display: block;
  margin: 12px 0 8px;
  color: var(--color-heading);
  font-size: 27px;
}

.event-summary strong.event-summary__time {
  font-size: 15px;
  line-height: 1.8;
}

.event-summary__critical {
  border-color: var(--color-danger-border) !important;
  background: var(--color-danger-soft) !important;
}

.event-summary__critical strong {
  color: var(--color-danger);
}

.event-list ol {
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.event-list li {
  display: grid;
  align-items: center;
  padding: 16px 0;
  grid-template-columns: 46px minmax(240px, 1fr) 130px 180px;
  gap: 16px;
  border-bottom: 1px solid var(--color-border-light);
}

.event-list li:last-child {
  border-bottom: 0;
}

.event-list__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.event-list__primary div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.event-list__primary strong {
  color: var(--color-heading);
  font-size: 14px;
}

.event-list__primary p {
  margin: 6px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
}

.event-list__metric span,
.event-list__metric small {
  display: block;
  color: var(--color-text-muted);
  font-size: 10px;
}

.event-list__metric strong {
  display: block;
  margin: 4px 0;
  color: var(--color-heading);
  font-size: 15px;
}

.event-list time {
  color: var(--color-text-secondary);
  font-size: 12px;
  text-align: right;
}

.event-pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  margin-top: 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.event-pagination {
  justify-content: flex-end;
}

.event-pagination :deep(.btn-prev),
.event-pagination :deep(.btn-next),
.event-pagination :deep(.el-pager li) {
  border: 1px solid var(--color-border);
  background: var(--color-control-bg) !important;
}

.event-pagination :deep(.el-pager li.is-active) {
  border-color: var(--color-primary);
  color: #fff;
  background: var(--color-primary) !important;
}

.event-loading,
.event-error {
  margin: 18px 0 0;
  padding: 32px;
  color: var(--color-text-muted);
  text-align: center;
}

.event-error {
  color: var(--color-danger);
}

@media (max-width: 1366px) {
  .event-summary {
    gap: 12px;
  }

  .event-list li {
    grid-template-columns: 42px minmax(220px, 1fr) 110px 155px;
  }
}
</style>
