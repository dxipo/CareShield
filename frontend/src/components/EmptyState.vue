<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
    icon: Component
    compact?: boolean
  }>(),
  {
    description: '',
    compact: false,
  },
)
</script>

<template>
  <div class="empty-state" :class="{ 'empty-state--compact': compact }">
    <span class="empty-state__icon" aria-hidden="true">
      <el-icon :size="32"><component :is="icon" /></el-icon>
    </span>
    <strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 250px;
  padding: 36px;
  flex-direction: column;
  text-align: center;
}

.empty-state--compact {
  min-height: 190px;
  padding: 24px;
}

.empty-state__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  border: 1px solid #dce7e2;
  border-radius: 18px;
  color: #648077;
  background: #f3f7f5;
}

strong {
  color: var(--color-heading);
  font-size: 15px;
  font-weight: 650;
}

p {
  max-width: 420px;
  margin: 8px 0 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.6;
}
</style>
