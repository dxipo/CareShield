<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    title: string
    value: string
    description: string
    icon: Component
    tone?: 'neutral' | 'success'
  }>(),
  {
    tone: 'neutral',
  },
)
</script>

<template>
  <article class="status-card" :class="`status-card--${tone}`">
    <div class="status-card__topline">
      <span class="status-card__icon" aria-hidden="true">
        <el-icon :size="19"><component :is="icon" /></el-icon>
      </span>
      <span class="status-card__label">{{ title }}</span>
    </div>
    <strong class="status-card__value">{{ value }}</strong>
    <p>{{ description }}</p>
  </article>
</template>

<style scoped>
.status-card {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.status-card__topline {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  color: #526b63;
  background: #eef3f1;
}

.status-card--success .status-card__icon {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.status-card__label {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-card__value {
  display: block;
  margin-top: 18px;
  color: var(--color-heading);
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
}

p {
  min-height: 20px;
  margin: 10px 0 0;
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
