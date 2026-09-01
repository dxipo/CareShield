import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '../layout/AppLayout.vue'

const DashboardView = () => import('../views/DashboardView.vue')
const AlgorithmsView = () => import('../views/AlgorithmsView.vue')
const DevicesView = () => import('../views/DevicesView.vue')
const EventsView = () => import('../views/EventsView.vue')
const FallDetectionView = () => import('../views/FallDetectionView.vue')
const FallRiskView = () => import('../views/FallRiskView.vue')
const FraudRiskView = () => import('../views/FraudRiskView.vue')
const ModulePlaceholderView = () => import('../views/ModulePlaceholderView.vue')
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
          path: 'fall-risk',
          name: 'fall-risk',
          component: FallRiskView,
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
          component: FraudRiskView,
          meta: {
            title: '诈骗风险',
            subtitle: '诈骗风险识别模块',
          },
        },
        {
          path: 'events',
          name: 'events',
          component: EventsView,
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
  const title = typeof to.meta.title === 'string' ? to.meta.title : '智安护居'
  document.title = `${title} · 智安护居`
})

export default router
