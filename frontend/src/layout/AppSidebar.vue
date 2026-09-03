<script setup lang="ts">
import {
  Bell,
  Camera,
  Cpu,
  DataBoard,
  Lock,
  Setting,
  TrendCharts,
  VideoCamera,
  Warning,
} from '@element-plus/icons-vue'
import { computed, markRaw, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { fetchAlgorithmsStatus } from '../api/algorithms'
import { fetchDevices } from '../api/devices'

const route = useRoute()
const platformHealthy = ref(false)
let healthTimer: ReturnType<typeof setInterval> | null = null

const platformStatusLabel = computed(() =>
  platformHealthy.value ? '设备与功能运行正常' : '部分设备离线或功能异常',
)

const navigation = [
  { path: '/dashboard', label: '综合首页', icon: markRaw(DataBoard) },
  { path: '/fall-risk', label: '跌倒风险', icon: markRaw(TrendCharts) },
  { path: '/fall-detection', label: '跌倒检测', icon: markRaw(Warning) },
  { path: '/fraud-risk', label: '诈骗风险', icon: markRaw(Lock) },
  { path: '/events', label: '风险事件', icon: markRaw(Bell) },
  { path: '/devices', label: '设备管理', icon: markRaw(Camera) },
  { path: '/algorithms', label: '算法管理', icon: markRaw(Cpu) },
  { path: '/system', label: '系统状态', icon: markRaw(Setting) },
]

async function refreshPlatformHealth(): Promise<void> {
  try {
    const [devices, algorithms] = await Promise.all([
      fetchDevices(),
      fetchAlgorithmsStatus(),
    ])
    const capabilityStates = Object.values(algorithms.capabilities)
    platformHealthy.value =
      devices.some((device) => device.online === true) &&
      algorithms.redis_reachable &&
      algorithms.workers.some((worker) => worker.online) &&
      capabilityStates.every((state) => state === 'running' || state === 'installed')
  } catch {
    platformHealthy.value = false
  }
}

onMounted(() => {
  void refreshPlatformHealth()
  healthTimer = setInterval(refreshPlatformHealth, 30_000)
})

onBeforeUnmount(() => {
  if (healthTimer) clearInterval(healthTimer)
})
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__brand">
      <span class="app-sidebar__brand-mark" aria-hidden="true">
        <el-icon :size="24"><VideoCamera /></el-icon>
      </span>
      <div>
        <strong>智安护居</strong>
        <span>CareShield Platform</span>
      </div>
    </div>

    <div class="app-sidebar__section-label">平台导航</div>
    <el-menu class="app-sidebar__menu" :default-active="route.path" router>
      <el-menu-item v-for="item in navigation" :key="item.path" :index="item.path">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </el-menu-item>
    </el-menu>

    <div class="app-sidebar__footer" :title="platformStatusLabel">
      <span
        class="app-sidebar__footer-dot"
        :class="{ 'app-sidebar__footer-dot--warning': !platformHealthy }"
        :aria-label="platformStatusLabel"
      ></span>
      <div>
        <strong>CareShield 智慧守护</strong>
        <span>多模态居家安全监护</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: sticky;
  top: 0;
  display: flex;
  width: 248px;
  height: 100vh;
  padding: 0 14px 18px;
  flex: 0 0 248px;
  flex-direction: column;
  color: var(--color-text-secondary);
  background: var(--color-sidebar);
  border-right: 1px solid var(--color-border);
}

.app-sidebar__brand {
  display: flex;
  align-items: center;
  height: 84px;
  padding: 0 10px;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
}

.app-sidebar__brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid var(--sidebar-logo-border);
  border-radius: 12px;
  color: var(--sidebar-logo-color);
  background: var(--color-primary-soft);
}

.app-sidebar__brand div,
.app-sidebar__footer div {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.app-sidebar__brand strong {
  color: var(--color-heading);
  font-size: 18px;
  letter-spacing: 0.08em;
}

.app-sidebar__brand span,
.app-sidebar__footer span {
  margin-top: 3px;
  color: var(--color-text-muted);
  font-size: 10px;
  letter-spacing: 0.04em;
}

.app-sidebar__section-label {
  padding: 26px 15px 10px;
  color: var(--sidebar-section-color);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.app-sidebar__menu {
  border-right: 0;
  background: transparent;
  --el-menu-text-color: var(--sidebar-nav-text);
  --el-menu-hover-text-color: var(--sidebar-nav-hover-text);
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: var(--sidebar-nav-hover-bg);
  --el-menu-active-color: var(--sidebar-nav-active-text);
}

.app-sidebar__menu :deep(.el-menu-item) {
  height: 46px;
  margin: 3px 0;
  border-radius: 9px;
  font-size: 13px;
}

.app-sidebar__menu :deep(.el-menu-item.is-active) {
  background: var(--sidebar-nav-active-bg);
}

.app-sidebar__menu :deep(.el-menu-item.is-active::before) {
  position: absolute;
  left: 0;
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--color-primary);
  content: "";
}

.app-sidebar__footer {
  display: flex;
  align-items: center;
  margin-top: auto;
  padding: 15px;
  gap: 11px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--sidebar-footer-bg);
}

.app-sidebar__footer strong {
  color: var(--sidebar-footer-text);
  font-size: 11px;
  font-weight: 600;
}

.app-sidebar__footer-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 4px rgb(34 160 107 / 10%);
  transition: background-color .2s ease, box-shadow .2s ease;
}

.app-sidebar__footer-dot--warning {
  background: var(--color-warning);
  box-shadow: 0 0 0 4px rgb(245 158 11 / 12%);
}

</style>
