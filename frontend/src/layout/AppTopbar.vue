<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const title = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : '颐安盾'))
const subtitle = computed(() =>
  typeof route.meta.subtitle === 'string' ? route.meta.subtitle : 'Elderly AI Safety Platform',
)
</script>

<template>
  <header class="app-topbar">
    <div>
      <h2>{{ title }}</h2>
      <p>{{ subtitle }}</p>
    </div>
    <div class="app-topbar__meta">
      <span class="app-topbar__phase">M1</span>
      <div>
        <strong>Elderly AI Safety Platform</strong>
        <span>Web platform foundation</span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 72px;
  padding: 0 30px;
  border-bottom: 1px solid var(--color-border);
  background: rgb(255 255 255 / 92%);
}

h2 {
  margin: 0;
  color: var(--color-heading);
  font-size: 16px;
  font-weight: 650;
}

p {
  margin: 5px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
}

.app-topbar__meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-topbar__phase {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  height: 27px;
  border: 1px solid #cce1d8;
  border-radius: 7px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
  font-size: 11px;
  font-weight: 750;
}

.app-topbar__meta div {
  display: flex;
  flex-direction: column;
}

.app-topbar__meta strong {
  color: var(--color-heading);
  font-size: 11px;
  font-weight: 650;
}

.app-topbar__meta div span {
  margin-top: 3px;
  color: var(--color-text-muted);
  font-size: 9px;
}

@media (max-width: 1450px) {
  .app-topbar {
    padding-right: 24px;
    padding-left: 24px;
  }
}
</style>
