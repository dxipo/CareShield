<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'

import BackendStatusPanel from '../components/BackendStatusPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
</script>

<template>
  <div>
    <PageHeader
      eyebrow="SYSTEM STATUS"
      title="系统状态"
      description="查看当前已开放的基础服务健康接口。仅 Backend 状态来自真实 API。"
    />

    <section class="system-grid">
      <BackendStatusPanel />
      <article class="panel-card">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">SERVICE VISIBILITY</span>
            <h2>其他服务</h2>
          </div>
        </div>
        <EmptyState
          compact
          title="暂无更多服务状态接口"
          description="PostgreSQL、Redis 与 AI Worker 尚未向前端提供业务状态 API。"
          :icon="Connection"
        />
      </article>
    </section>
  </div>
</template>

<style scoped>
.system-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
</style>
