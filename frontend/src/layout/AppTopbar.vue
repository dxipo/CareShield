<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { applyTheme, getActiveTheme, type AppTheme } from '../theme'

const route = useRoute()

const title = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : '智安护居'))
const subtitle = computed(() =>
  typeof route.meta.subtitle === 'string' ? route.meta.subtitle : 'CareShield',
)
const theme = ref<AppTheme>(getActiveTheme())
const nextThemeLabel = computed(() => theme.value === 'light' ? '切换深色模式' : '切换浅色模式')

function toggleTheme(): void {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  applyTheme(theme.value)
}
</script>

<template>
  <header class="app-topbar">
    <div>
      <h2>{{ title }}</h2>
      <p>{{ subtitle }}</p>
    </div>
    <div class="app-topbar__actions">
      <el-button
        class="app-topbar__theme"
        :icon="theme === 'light' ? Moon : Sunny"
        :aria-label="nextThemeLabel"
        :title="nextThemeLabel"
        @click="toggleTheme"
      >
        {{ theme === 'light' ? '深色模式' : '浅色模式' }}
      </el-button>
      <div class="app-topbar__meta">
        <div>
          <strong>CareShield</strong>
          <span>Smart elderly care &amp; safety</span>
        </div>
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
  background: var(--color-topbar);
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

.app-topbar__actions,
.app-topbar__meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-topbar__theme {
  min-width: 98px;
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
