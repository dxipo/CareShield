import { createApp } from 'vue'
import {
  ElButton,
  ElDescriptions,
  ElDescriptionsItem,
  ElDrawer,
  ElIcon,
  ElMenu,
  ElMenuItem,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'
import '@ezuikit/player-hls/dist/style/css.js'

import App from './App.vue'
import router from './router'
import './style.css'

createApp(App)
  .use(router)
  .use(ElButton)
  .use(ElDescriptions)
  .use(ElDescriptionsItem)
  .use(ElDrawer)
  .use(ElIcon)
  .use(ElMenu)
  .use(ElMenuItem)
  .use(ElTable)
  .use(ElTableColumn)
  .use(ElTag)
  .mount('#app')
