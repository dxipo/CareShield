import { createApp } from 'vue'
import {
  ElButton,
  ElDescriptions,
  ElDescriptionsItem,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElMenu,
  ElMenuItem,
  ElPagination,
  ElProgress,
  ElRadio,
  ElRadioGroup,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './style.css'
import { initializeTheme } from './theme'

initializeTheme()

createApp(App)
  .use(router)
  .use(ElButton)
  .use(ElDescriptions)
  .use(ElDescriptionsItem)
  .use(ElDrawer)
  .use(ElEmpty)
  .use(ElIcon)
  .use(ElInput)
  .use(ElInputNumber)
  .use(ElMenu)
  .use(ElMenuItem)
  .use(ElPagination)
  .use(ElProgress)
  .use(ElRadio)
  .use(ElRadioGroup)
  .use(ElTable)
  .use(ElTableColumn)
  .use(ElTag)
  .mount('#app')
