<script setup lang="ts">
import {
  Camera,
  Connection,
  Loading,
  Refresh,
  View,
  Warning,
} from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  ApiRequestError,
  fetchDeviceDetail,
  fetchDevices,
  fetchEzvizStatus,
  type DeviceDetail,
  type DeviceSummary,
  type EzvizIntegrationStatus,
} from '../api/devices'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'

type PageState = 'loading' | 'unconfigured' | 'empty' | 'error' | 'ready'

const pageState = ref<PageState>('loading')
const devices = ref<DeviceSummary[]>([])
const integration = ref<EzvizIntegrationStatus | null>(null)
const errorMessage = ref('')
const refreshedAt = ref<Date | null>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedDevice = ref<DeviceDetail | null>(null)
const detailError = ref('')
let pageController: AbortController | null = null
let detailController: AbortController | null = null

const onlineCount = computed(() => devices.value.filter((device) => device.online === true).length)

async function refreshDevices() {
  pageController?.abort()
  pageController = new AbortController()
  pageState.value = 'loading'
  errorMessage.value = ''

  try {
    const status = await fetchEzvizStatus(pageController.signal)
    integration.value = status

    if (!status.configured) {
      devices.value = []
      pageState.value = 'unconfigured'
      return
    }
    if (!status.reachable) {
      throw new Error(status.message || '无法连接萤石开放平台')
    }

    devices.value = await fetchDevices(pageController.signal)
    refreshedAt.value = new Date()
    pageState.value = devices.value.length === 0 ? 'empty' : 'ready'
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    errorMessage.value = readableError(error)
    pageState.value = 'error'
  }
}

async function showDetail(device: DeviceSummary) {
  detailController?.abort()
  detailController = new AbortController()
  selectedDevice.value = null
  detailError.value = ''
  detailVisible.value = true
  detailLoading.value = true

  try {
    selectedDevice.value = await fetchDeviceDetail(device.device_serial, detailController.signal)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    detailError.value = readableError(error)
  } finally {
    detailLoading.value = false
  }
}

function readableError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '请检查 Backend 配置与网络连接后重试'
}

function maskSerial(serial: string): string {
  if (serial.length <= 4) return '••••'
  return `•••• ${serial.slice(-4)}`
}

function redactSerial(value: string | null, serial: string): string | null {
  if (!value) return null
  return value.split(serial).join(maskSerial(serial))
}

function displayDeviceName(device: DeviceSummary): string {
  return redactSerial(device.name, device.device_serial) || '未命名设备'
}

function formatDate(value: string | Date | null): string {
  if (!value) return '--'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function statusLabel(device: DeviceSummary): string {
  if (device.online === true) return 'Online'
  if (device.online === false) return 'Offline'
  return 'Unknown'
}

function statusType(device: DeviceSummary): 'success' | 'info' | 'warning' {
  if (device.online === true) return 'success'
  if (device.online === false) return 'info'
  return 'warning'
}

onMounted(refreshDevices)
onBeforeUnmount(() => {
  pageController?.abort()
  detailController?.abort()
})
</script>

<template>
  <div class="devices-view">
    <PageHeader
      eyebrow="DEVICE INTEGRATION"
      title="设备管理"
      description="通过 CareShield Backend 查询当前萤石开放平台账号下的真实设备。设备序列号在界面中默认脱敏。"
    />

    <article class="panel-card devices-panel">
      <div class="devices-toolbar">
        <div class="devices-toolbar__identity">
          <span class="devices-toolbar__icon">
            <el-icon :size="20"><Connection /></el-icon>
          </span>
          <div>
            <span class="devices-toolbar__label">设备平台</span>
            <strong>EZVIZ 萤石开放平台</strong>
          </div>
          <el-tag
            v-if="integration"
            :type="integration.reachable ? 'success' : 'info'"
            effect="plain"
          >
            {{ integration.reachable ? 'Connected' : 'Not connected' }}
          </el-tag>
        </div>
        <div class="devices-toolbar__actions">
          <span v-if="refreshedAt" class="devices-toolbar__time">
            最近刷新 {{ formatDate(refreshedAt) }}
          </span>
          <el-button :disabled="pageState === 'loading'" :icon="Refresh" @click="refreshDevices">
            刷新
          </el-button>
        </div>
      </div>

      <div v-if="pageState === 'loading'" class="devices-loading">
        <el-icon class="is-loading" :size="30"><Loading /></el-icon>
        <strong>正在获取设备...</strong>
        <span>正在通过 Backend 连接萤石开放平台</span>
      </div>

      <EmptyState
        v-else-if="pageState === 'unconfigured'"
        title="萤石开放平台尚未配置"
        description="请在本机 .env 中配置 EZVIZ_APP_KEY 和 EZVIZ_APP_SECRET，并重启 Backend。"
        :icon="Connection"
      />

      <EmptyState
        v-else-if="pageState === 'empty'"
        title="当前萤石账号下暂无设备"
        description="Backend 已成功连接萤石开放平台，但账号下未查询到设备。"
        :icon="Camera"
      />

      <div v-else-if="pageState === 'error'" class="devices-error">
        <EmptyState
          title="设备数据获取失败"
          :description="errorMessage"
          :icon="Warning"
        />
        <el-button :icon="Refresh" @click="refreshDevices">重新获取</el-button>
      </div>

      <template v-else>
        <div class="devices-summary">
          <span>共 {{ devices.length }} 台真实设备</span>
          <span class="devices-summary__divider" />
          <span>{{ onlineCount }} 台在线</span>
        </div>
        <el-table :data="devices" class="devices-table" row-key="id">
          <el-table-column label="平台" width="110">
            <template #default>
              <el-tag effect="plain">EZVIZ</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="设备名称" min-width="190">
            <template #default="scope">
              <div class="device-name-cell">
                <strong>{{ displayDeviceName(scope.row) }}</strong>
                <span>{{ maskSerial(scope.row.device_serial) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="设备型号" min-width="170">
            <template #default="scope">{{ scope.row.model || '--' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="scope">
              <el-tag :type="statusType(scope.row)" effect="light" round>
                {{ statusLabel(scope.row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="设备类型" min-width="130">
            <template #default="scope">{{ scope.row.device_type || '--' }}</template>
          </el-table-column>
          <el-table-column label="Camera / Channel" min-width="160">
            <template #default="scope">
              {{ scope.row.camera_count === null ? '--' : `${scope.row.camera_count} 路` }}
            </template>
          </el-table-column>
          <el-table-column label="设备更新时间" min-width="190">
            <template #default="scope">{{ formatDate(scope.row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button link type="primary" :icon="View" @click="showDetail(scope.row)">
                查看详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </article>

    <el-drawer v-model="detailVisible" title="设备详情" size="430px">
      <div v-if="detailLoading" class="detail-loading">
        <el-icon class="is-loading" :size="26"><Loading /></el-icon>
        <span>正在获取设备详情...</span>
      </div>
      <div v-else-if="detailError" class="detail-error">
        <el-icon :size="26"><Warning /></el-icon>
        <strong>设备详情获取失败</strong>
        <span>{{ detailError }}</span>
      </div>
      <el-descriptions v-else-if="selectedDevice" :column="1" border>
        <el-descriptions-item label="平台">EZVIZ</el-descriptions-item>
        <el-descriptions-item label="设备名称">
          {{ redactSerial(selectedDevice.name, selectedDevice.device_serial) || '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="设备序列号">
          {{ maskSerial(selectedDevice.device_serial) }}
        </el-descriptions-item>
        <el-descriptions-item label="设备型号">
          {{ selectedDevice.model || '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="设备类型">
          {{ selectedDevice.device_type || '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusType(selectedDevice)" effect="light">
            {{ statusLabel(selectedDevice) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.local_name" label="设备上报名称">
          {{ redactSerial(selectedDevice.local_name, selectedDevice.device_serial) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.firmware_version" label="固件版本">
          {{ selectedDevice.firmware_version }}
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.network_type" label="网络类型">
          {{ selectedDevice.network_type }}
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.signal" label="信号强度">
          {{ selectedDevice.signal }}
        </el-descriptions-item>
        <el-descriptions-item v-if="selectedDevice.camera_count !== null" label="Camera / Channel">
          {{ selectedDevice.camera_count }} 路
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ formatDate(selectedDevice.updated_at) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.devices-panel {
  padding: 0;
  overflow: hidden;
}

.devices-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 78px;
  padding: 16px 20px;
  gap: 20px;
  border-bottom: 1px solid var(--color-border-light);
}

.devices-toolbar__identity,
.devices-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.devices-toolbar__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.devices-toolbar__identity strong,
.device-name-cell strong {
  display: block;
  color: var(--color-heading);
  font-size: 14px;
  font-weight: 650;
}

.devices-toolbar__label,
.device-name-cell span,
.devices-toolbar__time {
  display: block;
  color: var(--color-text-muted);
  font-size: 11px;
}

.devices-loading,
.detail-loading,
.detail-error {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 270px;
  flex-direction: column;
  gap: 10px;
  color: var(--color-neutral-icon);
}

.devices-loading strong,
.detail-error strong {
  color: var(--color-heading);
  font-size: 15px;
}

.devices-loading span,
.detail-loading span,
.detail-error span {
  max-width: 320px;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.devices-error {
  position: relative;
  text-align: center;
}

.devices-error :deep(.empty-state) {
  padding-bottom: 18px;
}

.devices-error > .el-button {
  margin-bottom: 36px;
}

.devices-summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 0 20px;
  gap: 12px;
  color: var(--color-text-secondary);
  font-size: 12px;
  background: var(--color-surface-soft);
}

.devices-summary__divider {
  width: 1px;
  height: 13px;
  background: var(--color-border);
}

.devices-table {
  width: 100%;
}

.devices-table :deep(th.el-table__cell) {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 650;
  background: var(--color-surface-soft);
}

.devices-table :deep(td.el-table__cell) {
  padding-top: 14px;
  padding-bottom: 14px;
}

.devices-table :deep(.el-table-fixed-column--right) {
  background: var(--color-fixed-column) !important;
  box-shadow: -8px 0 14px rgb(31 41 55 / 5%);
}

.device-name-cell span {
  margin-top: 5px;
  letter-spacing: 0.04em;
}

.detail-error {
  min-height: 220px;
  color: var(--color-danger);
}

@media (max-width: 1450px) {
  .devices-toolbar__time {
    display: none;
  }
}
</style>
