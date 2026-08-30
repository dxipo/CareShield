<script setup lang="ts">
import { EZUIKitPlayer, type EZUIKitError } from 'ezuikit-js'
import { Refresh, VideoCamera } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchDevices, type DeviceSummary } from '../api/devices'
import { fetchBrowserPlaybackSession, type BrowserPlaybackSession } from '../api/streams'

type PreviewState = 'loading' | 'connecting' | 'live' | 'offline' | 'unavailable' | 'error'

const state = ref<PreviewState>('loading')
const device = ref<DeviceSummary | null>(null)
const protocol = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const playerContainer = ref<HTMLElement | null>(null)
const playerContainerId = 'careshield-dashboard-ezopen-player'
let player: EZUIKitPlayer | null = null
let requestController: AbortController | null = null
let resizeObserver: ResizeObserver | null = null
let playerGeneration = 0

const stateLabel = computed(() => {
  const labels: Record<PreviewState, string> = {
    loading: '正在获取设备...',
    connecting: '正在连接摄像头...',
    live: 'LIVE',
    offline: '摄像头当前离线',
    unavailable: '暂时无法获取实时视频',
    error: '实时视频播放失败',
  }
  return labels[state.value]
})

const deviceDisplayName = computed(() => {
  const current = device.value
  if (!current) return 'EZVIZ Camera'
  if (current.name && current.device_serial && current.name.includes(current.device_serial)) {
    return current.name.replace(current.device_serial, `••••${current.device_serial.slice(-4)}`)
  }
  return current.name || current.model || 'EZVIZ Camera'
})

function pickDevice(devices: DeviceSummary[]): DeviceSummary | null {
  const h6c = devices.find((item) =>
    `${item.model ?? ''} ${item.name ?? ''}`.toLowerCase().includes('h6c'),
  )
  return h6c ?? devices.find((item) => item.online === true) ?? devices[0] ?? null
}

function destroyPlayer(): void {
  playerGeneration += 1
  resizeObserver?.disconnect()
  resizeObserver = null
  if (player) {
    const stalePlayer = player
    player = null
    void stalePlayer.stop().catch(() => undefined)
    stalePlayer.destroy()
  }
  playerContainer.value?.replaceChildren()
}

async function initializePlayer(session: BrowserPlaybackSession): Promise<void> {
  await nextTick()
  const container = playerContainer.value
  if (!container) throw new Error('Player container is unavailable')

  destroyPlayer()
  const generation = playerGeneration
  const currentPlayer = new EZUIKitPlayer({
    id: playerContainerId,
    accessToken: session.access_token,
    url: session.playback_url,
    width: Math.max(container.clientWidth, 640),
    height: Math.max(container.clientHeight, 360),
    template: 'pcLive',
    audio: true,
    autoPlay: true,
    decoderType: 'v3',
    staticPath: '/ezuikit_static',
    quality: 'pp',
    language: 'zh',
    disableRenderPrivateData: true,
    streamInfoCBType: 1,
    loggerOptions: { name: 'CareShield Dashboard EZOPEN', level: 'WARN', showTime: false },
    handleError: (error: EZUIKitError) => {
      if (playerGeneration !== generation) return
      state.value = 'error'
      const errorCode = error.data?.nErrorCode
      errorMessage.value = `EZOPEN 播放异常${errorCode === undefined ? '' : ` (${errorCode})`}`
    },
  })

  player = currentPlayer
  currentPlayer.eventEmitter.on(EZUIKitPlayer.EVENTS.firstFrameDisplay, () => {
    if (playerGeneration !== generation) return
    errorMessage.value = null
    state.value = 'live'
  })

  resizeObserver = new ResizeObserver(([entry]) => {
    if (!entry || player !== currentPlayer) return
    currentPlayer.resize(
      Math.max(entry.contentRect.width, 1),
      Math.max(entry.contentRect.height, 1),
    )
  })
  resizeObserver.observe(container)
}

async function connect(): Promise<void> {
  requestController?.abort()
  destroyPlayer()
  requestController = new AbortController()
  const { signal } = requestController
  state.value = 'loading'
  protocol.value = null
  errorMessage.value = null

  try {
    const devices = await fetchDevices(signal)
    const selected = pickDevice(devices)
    device.value = selected
    if (!selected) {
      state.value = 'unavailable'
      return
    }
    if (selected.online !== true) {
      state.value = 'offline'
      return
    }

    const channelNo = selected.channels.find((channel) => channel.number)?.number ?? 1
    state.value = 'connecting'
    const session = await fetchBrowserPlaybackSession(selected.device_serial, channelNo, signal)
    protocol.value = session.protocol.toUpperCase()
    await initializePlayer(session)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      state.value = 'unavailable'
      errorMessage.value = '无法创建安全的 EZOPEN 播放会话'
    }
  }
}

onMounted(() => void connect())
onBeforeUnmount(() => {
  requestController?.abort()
  destroyPlayer()
})
</script>

<template>
  <div class="dashboard-live">
    <div class="dashboard-live__viewport">
      <div :id="playerContainerId" ref="playerContainer" class="dashboard-live__player"></div>
      <div v-if="state !== 'live'" class="dashboard-live__placeholder">
        <el-icon :size="34"><VideoCamera /></el-icon>
        <strong>{{ stateLabel }}</strong>
        <span v-if="errorMessage">{{ errorMessage }}</span>
        <el-button v-if="state !== 'loading' && state !== 'connecting'" :icon="Refresh" @click="connect">
          重新连接
        </el-button>
      </div>
      <div v-if="state === 'live'" class="dashboard-live__status">
        <span><i></i> LIVE</span>
        <span>{{ protocol }}</span>
      </div>
    </div>
    <div class="dashboard-live__footer">
      <div>
        <strong>{{ deviceDisplayName }}</strong>
        <span>{{ device?.model || 'EZVIZ Camera' }}</span>
      </div>
      <router-link to="/monitor">进入实时监测</router-link>
    </div>
  </div>
</template>

<style scoped>
.dashboard-live {
  margin-top: 18px;
}

.dashboard-live__viewport {
  position: relative;
  min-height: 326px;
  overflow: hidden;
  border: 1px solid #283c37;
  border-radius: 11px;
  background: #0c1513;
}

.dashboard-live__player {
  width: 100%;
  min-height: 326px;
}

.dashboard-live__placeholder {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  color: #9db2ab;
  background: radial-gradient(circle at center, #1a2c27 0, #0c1513 72%);
}

.dashboard-live__placeholder strong {
  color: #e4efeb;
  font-size: 14px;
}

.dashboard-live__placeholder span {
  color: #8fa49d;
  font-size: 11px;
}

.dashboard-live__status {
  position: absolute;
  z-index: 3;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 7px;
}

.dashboard-live__status span {
  padding: 5px 8px;
  border: 1px solid rgb(255 255 255 / 20%);
  border-radius: 6px;
  color: #f2f7f5;
  background: rgb(8 20 17 / 76%);
  font-size: 10px;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.dashboard-live__status i {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-radius: 50%;
  background: #63d4a5;
}

.dashboard-live__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 2px 0;
}

.dashboard-live__footer div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.dashboard-live__footer strong {
  overflow: hidden;
  color: var(--color-heading);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-live__footer span,
.dashboard-live__footer a {
  color: var(--color-text-muted);
  font-size: 10px;
}

.dashboard-live__footer a {
  color: var(--color-primary);
  font-weight: 650;
  text-decoration: none;
}
</style>
