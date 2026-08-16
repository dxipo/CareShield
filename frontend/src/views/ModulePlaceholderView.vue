<script setup lang="ts">
import { Bell, Camera, Cpu, Lock, TrendCharts, Warning } from '@element-plus/icons-vue'
import { computed, markRaw, type Component } from 'vue'

import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'

type IconName = 'trend' | 'warning' | 'lock' | 'bell' | 'camera' | 'cpu'

const props = defineProps<{
  title: string
  description: string
  emptyTitle: string
  emptyDescription: string
  iconName: IconName
}>()

const icons: Record<IconName, Component> = {
  trend: markRaw(TrendCharts),
  warning: markRaw(Warning),
  lock: markRaw(Lock),
  bell: markRaw(Bell),
  camera: markRaw(Camera),
  cpu: markRaw(Cpu),
}

const icon = computed(() => icons[props.iconName])
</script>

<template>
  <div>
    <PageHeader eyebrow="MODULE OVERVIEW" :title="title" :description="description" />
    <section class="panel-card module-placeholder">
      <EmptyState :title="emptyTitle" :description="emptyDescription" :icon="icon" />
    </section>
  </div>
</template>

<style scoped>
.module-placeholder {
  min-height: 520px;
}

.module-placeholder :deep(.empty-state) {
  min-height: 470px;
}
</style>
