import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '../layout/AppLayout.vue'

const DashboardView = () => import('../views/DashboardView.vue')
const AlgorithmsView = () => import('../views/AlgorithmsView.vue')
const DevicesView = () => import('../views/DevicesView.vue')
const FallDetectionView = () => import('../views/FallDetectionView.vue')
const ModulePlaceholderView = () => import('../views/ModulePlaceholderView.vue')
const MonitorView = () => import('../views/MonitorView.vue')
const SystemView = () => import('../views/SystemView.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: DashboardView,
          meta: {
            title: '综合首页',
            subtitle: '居家老人安全态势与平台运行概览',
          },
        },
        {
          path: 'monitor',
          name: 'monitor',
          component: MonitorView,
          meta: {
            title: '实时监测',
            subtitle: '设备实时画面与状态入口',
          },
        },
        {
          path: 'fall-risk',
          name: 'fall-risk',
          component: ModulePlaceholderView,
          props: {
            title: '跌倒风险',
            description: '用于未来呈现跌倒风险评估结果与风险变化。',
            emptyTitle: '跌倒风险模型尚未接入',
            emptyDescription: '当前阶段不提供评估数值或模拟结果。',
            iconName: 'trend',
          },
          meta: {
            title: '跌倒风险',
            subtitle: '跌倒风险评估模块',
          },
        },
        {
          path: 'fall-detection',
          name: 'fall-detection',
          component: FallDetectionView,
          meta: {
            title: '跌倒检测',
            subtitle: '实时跌倒检测模块',
          },
        },
        {
          path: 'fraud-risk',
          name: 'fraud-risk',
          component: ModulePlaceholderView,
          props: {
            title: '诈骗风险',
            description: '用于未来呈现通话与场景中的诈骗风险识别结果。',
            emptyTitle: '诈骗风险模型尚未接入',
            emptyDescription: '当前阶段不采集音频，也不生成风险判断。',
            iconName: 'lock',
          },
          meta: {
            title: '诈骗风险',
            subtitle: '诈骗风险识别模块',
          },
        },
        {
          path: 'events',
          name: 'events',
          component: ModulePlaceholderView,
          props: {
            title: '风险事件',
            description: '统一查看未来由各风险模块产生的事件记录。',
            emptyTitle: '暂无风险事件',
            emptyDescription: '业务事件能力尚未接入。',
            iconName: 'bell',
          },
          meta: {
            title: '风险事件',
            subtitle: '平台风险事件中心',
          },
        },
        {
          path: 'devices',
          name: 'devices',
          component: DevicesView,
          meta: {
            title: '设备管理',
            subtitle: '摄像设备与接入状态',
          },
        },
        {
          path: 'algorithms',
          name: 'algorithms',
          component: AlgorithmsView,
          meta: {
            title: '算法管理',
            subtitle: 'AI Worker 与算法模块',
          },
        },
        {
          path: 'system',
          name: 'system',
          component: SystemView,
          meta: {
            title: '系统状态',
            subtitle: '基础服务连通性与接入状态',
          },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : '颐安盾'
  document.title = `${title} · 颐安盾`
})

export default router
