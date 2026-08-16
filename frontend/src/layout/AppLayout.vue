<script setup lang="ts">
import { RouterView } from 'vue-router'

import AppSidebar from './AppSidebar.vue'
import AppTopbar from './AppTopbar.vue'
</script>

<template>
  <div class="app-layout">
    <AppSidebar />
    <div class="app-layout__workspace">
      <AppTopbar />
      <main class="app-layout__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  min-width: 1180px;
  min-height: 100vh;
  background: var(--color-page);
}

.app-layout__workspace {
  display: flex;
  min-width: 0;
  min-height: 100vh;
  flex: 1;
  flex-direction: column;
}

.app-layout__content {
  width: 100%;
  max-width: 1680px;
  margin: 0 auto;
  padding: 28px 30px 40px;
}

@media (max-width: 1450px) {
  .app-layout__content {
    padding-right: 24px;
    padding-left: 24px;
  }
}
</style>
