<script setup lang="ts">
import { CircleCheck, Refresh, Warning } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchBackendHealth, type HealthResponse } from '../api/health'

type Availability = 'checking' | 'online' | 'offline'

const availability = ref<Availability>('checking')
const health = ref<HealthResponse | null>(null)
const isRefreshing = ref(false)
let controller: AbortController | null = null

const statusLabel = computed(() => {
  if (availability.value === 'online') return 'Online'
  if (availability.value === 'offline') return 'Offline'
  return 'Checking'
})

const statusDetail = computed(() => {
  if (availability.value === 'online') return 'FastAPI 基础服务响应正常'
  if (availability.value === 'offline') return '无法连接 Backend，请检查服务状态'
  return '正在检查 Backend 连通性'
})

async function checkHealth(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  isRefreshing.value = true
  availability.value = 'checking'

  try {
    const result = await fetchBackendHealth(controller.signal)
    health.value = result
    availability.value = result.status === 'ok' ? 'online' : 'offline'
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    health.value = null
    availability.value = 'offline'
  } finally {
    isRefreshing.value = false
  }
}

onMounted(checkHealth)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="backend-status panel-card">
    <div class="panel-card__header">
      <div>
        <span class="panel-card__kicker">SYSTEM HEALTH</span>
        <h2>系统运行状态</h2>
      </div>
      <el-button
        :icon="Refresh"
        :loading="isRefreshing"
        circle
        plain
        aria-label="重新检查 Backend 状态"
        @click="checkHealth"
      />
    </div>

    <div class="backend-status__content">
      <span
        class="backend-status__indicator"
        :class="`backend-status__indicator--${availability}`"
        aria-hidden="true"
      >
        <el-icon :size="26">
          <CircleCheck v-if="availability === 'online'" />
          <Warning v-else />
        </el-icon>
      </span>
      <div>
        <div class="backend-status__headline">
          <span>Backend</span>
          <el-tag
            :type="availability === 'online' ? 'success' : availability === 'offline' ? 'danger' : 'info'"
            effect="light"
            round
          >
            {{ statusLabel }}
          </el-tag>
        </div>
        <p>{{ statusDetail }}</p>
      </div>
    </div>

    <dl class="backend-status__meta">
      <div>
        <dt>Health endpoint</dt>
        <dd>GET /api/health</dd>
      </div>
      <div>
        <dt>Service</dt>
        <dd>{{ health?.service ?? '--' }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.backend-status {
  height: 100%;
}

.backend-status__content {
  display: grid;
  align-items: center;
  grid-template-columns: 54px 1fr;
  gap: 15px;
  padding: 24px 0;
}

.backend-status__indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 15px;
  color: #70837c;
  background: #f1f4f3;
}

.backend-status__indicator--online {
  color: var(--color-success);
  background: #eaf7f0;
}

.backend-status__indicator--offline {
  color: var(--color-danger);
  background: #fff0ee;
}

.backend-status__headline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-heading);
  font-size: 16px;
  font-weight: 650;
}

.backend-status__content p {
  margin: 7px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.backend-status__meta {
  display: grid;
  margin: 0;
  border-top: 1px solid var(--color-border-light);
  grid-template-columns: 1fr 1fr;
}

.backend-status__meta div {
  padding: 16px 0 0;
}

.backend-status__meta div + div {
  padding-left: 18px;
  border-left: 1px solid var(--color-border-light);
}

dt {
  color: var(--color-text-muted);
  font-size: 11px;
}

dd {
  margin: 5px 0 0;
  color: var(--color-heading);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
}
</style>
