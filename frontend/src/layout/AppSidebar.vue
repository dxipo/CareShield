<script setup lang="ts">
import {
  Bell,
  Camera,
  Cpu,
  DataBoard,
  Lock,
  Monitor,
  Setting,
  TrendCharts,
  VideoCamera,
  Warning,
} from '@element-plus/icons-vue'
import { markRaw } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const navigation = [
  { path: '/dashboard', label: '综合首页', icon: markRaw(DataBoard) },
  { path: '/monitor', label: '实时监测', icon: markRaw(Monitor) },
  { path: '/fall-risk', label: '跌倒风险', icon: markRaw(TrendCharts) },
  { path: '/fall-detection', label: '跌倒检测', icon: markRaw(Warning) },
  { path: '/fraud-risk', label: '诈骗风险', icon: markRaw(Lock) },
  { path: '/events', label: '风险事件', icon: markRaw(Bell) },
  { path: '/devices', label: '设备管理', icon: markRaw(Camera) },
  { path: '/algorithms', label: '算法管理', icon: markRaw(Cpu) },
  { path: '/system', label: '系统状态', icon: markRaw(Setting) },
]
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__brand">
      <span class="app-sidebar__brand-mark" aria-hidden="true">
        <el-icon :size="24"><VideoCamera /></el-icon>
      </span>
      <div>
        <strong>颐安盾</strong>
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

    <div class="app-sidebar__footer">
      <span class="app-sidebar__footer-dot" aria-hidden="true"></span>
      <div>
        <strong>M4 Realtime Pipeline</strong>
        <span>AI 结果实时基础设施</span>
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
  color: #d9e5e0;
  background: #142b27;
}

.app-sidebar__brand {
  display: flex;
  align-items: center;
  height: 84px;
  padding: 0 10px;
  gap: 12px;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
}

.app-sidebar__brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid rgb(149 209 185 / 32%);
  border-radius: 12px;
  color: #a9dec8;
  background: rgb(83 160 129 / 16%);
}

.app-sidebar__brand div,
.app-sidebar__footer div {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.app-sidebar__brand strong {
  color: #ffffff;
  font-size: 18px;
  letter-spacing: 0.08em;
}

.app-sidebar__brand span,
.app-sidebar__footer span {
  margin-top: 3px;
  color: #8fa8a0;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.app-sidebar__section-label {
  padding: 26px 15px 10px;
  color: #718c83;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.app-sidebar__menu {
  border-right: 0;
  background: transparent;
  --el-menu-text-color: #aec0ba;
  --el-menu-hover-text-color: #ffffff;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgb(255 255 255 / 6%);
  --el-menu-active-color: #dff7ed;
}

.app-sidebar__menu :deep(.el-menu-item) {
  height: 46px;
  margin: 3px 0;
  border-radius: 9px;
  font-size: 13px;
}

.app-sidebar__menu :deep(.el-menu-item.is-active) {
  background: rgb(74 157 125 / 23%);
}

.app-sidebar__menu :deep(.el-menu-item.is-active::before) {
  position: absolute;
  left: 0;
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: #75c9a8;
  content: "";
}

.app-sidebar__footer {
  display: flex;
  align-items: center;
  margin-top: auto;
  padding: 15px;
  gap: 11px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 10px;
  background: rgb(255 255 255 / 3%);
}

.app-sidebar__footer strong {
  color: #d9e5e0;
  font-size: 11px;
  font-weight: 600;
}

.app-sidebar__footer-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #67c99f;
  box-shadow: 0 0 0 4px rgb(103 201 159 / 12%);
}
</style>
