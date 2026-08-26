<script setup lang="ts">
import { EZUIKitPlayer, type EZUIKitError } from 'ezuikit-js'
import { Refresh, VideoCamera } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchDevices, type DeviceSummary } from '../api/devices'
import {
  fetchBrowserPlaybackSession,
  fetchMediaInfo,
  type BrowserPlaybackSession,
  type MediaInfo,
} from '../api/streams'
import PageHeader from '../components/PageHeader.vue'

type MonitorState = 'loading' | 'connecting' | 'live' | 'offline' | 'unavailable' | 'error'

const state = ref<MonitorState>('loading')
const selectedDevice = ref<DeviceSummary | null>(null)
const protocol = ref<string | null>(null)
const activeDecoder = ref<string | null>(null)
const firstFrameLatencyMs = ref<number | null>(null)
const playbackError = ref<string | null>(null)
const diagnostics = ref<MediaInfo | null>(null)
const diagnosticsLoading = ref(false)
const playerContainer = ref<HTMLElement | null>(null)
const playerContainerId = 'careshield-ezopen-player'
let player: EZUIKitPlayer | null = null
let requestController: AbortController | null = null
let resizeObserver: ResizeObserver | null = null
let playerGeneration = 0

const stateLabel = computed(() => {
  const labels: Record<MonitorState, string> = {
    loading: 'Loading',
    connecting: 'Connecting',
    live: 'LIVE',
    offline: 'Offline',
    unavailable: 'Unavailable',
    error: 'Stream Error',
  }
  return labels[state.value]
})

const stateTagType = computed(() => {
  if (state.value === 'live') return 'success'
  if (state.value === 'offline' || state.value === 'error') return 'danger'
  return 'info'
})

const placeholderMessage = computed(() => {
  if (state.value === 'loading') return '正在获取设备...'
  if (state.value === 'connecting') return '正在通过 EZOPEN 连接摄像头...'
  if (state.value === 'offline') return '摄像头当前离线'
  if (state.value === 'error') return '实时流连接失败，请尝试重新连接'
  return '暂时无法获取实时视频'
})

const deviceDisplayName = computed(() => {
  const device = selectedDevice.value
  if (!device) return 'EZVIZ Camera'
  if (device.name && device.device_serial && device.name.includes(device.device_serial)) {
    return device.name.replace(device.device_serial, `••••${device.device_serial.slice(-4)}`)
  }
  return device.name || device.model || 'EZVIZ Camera'
})

const resolution = computed(() => {
  const video = diagnostics.value?.video
  return video?.width && video.height ? `${video.width} × ${video.height}` : 'Not probed'
})

function pickDevice(devices: DeviceSummary[]): DeviceSummary | null {
  const h6c = devices.find((device) =>
    `${device.model ?? ''} ${device.name ?? ''}`.toLowerCase().includes('h6c'),
  )
  return h6c ?? devices.find((device) => device.online === true) ?? devices[0] ?? null
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

async function initializePlayer(
  session: BrowserPlaybackSession,
  connectionStartedAt: number,
): Promise<void> {
  await nextTick()
  const container = playerContainer.value
  if (!container) throw new Error('Player container is unavailable')

  destroyPlayer()
  const generation = playerGeneration
  const width = Math.max(container.clientWidth, 640)
  const height = Math.max(container.clientHeight, 360)
  const currentPlayer = new EZUIKitPlayer({
    id: playerContainerId,
    accessToken: session.access_token,
    url: session.playback_url,
    width,
    height,
    template: 'pcLive',
    audio: true,
    autoPlay: true,
    decoderType: 'v3',
    staticPath: '/ezuikit_static',
    quality: 'pp',
    language: 'zh',
    disableRenderPrivateData: true,
    streamInfoCBType: 1,
    loggerOptions: { name: 'CareShield EZOPEN', level: 'WARN', showTime: false },
    handleError: (error: EZUIKitError) => {
      if (playerGeneration !== generation) return
      state.value = 'error'
      const errorType = error.type || 'unknown'
      const errorCode = error.data?.nErrorCode
      playbackError.value = `EZOPEN 播放异常：${errorType}${errorCode === undefined ? '' : ` (${errorCode})`}`
    },
  })

  player = currentPlayer
  activeDecoder.value = session.decoder
  currentPlayer.eventEmitter.on(EZUIKitPlayer.EVENTS.firstFrameDisplay, () => {
    if (playerGeneration !== generation) return
    firstFrameLatencyMs.value = Math.round(performance.now() - connectionStartedAt)
    playbackError.value = null
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

async function loadDiagnostics(device: DeviceSummary, channelNo: number, signal: AbortSignal) {
  diagnosticsLoading.value = true
  diagnostics.value = null
  try {
    diagnostics.value = await fetchMediaInfo(device.device_serial, channelNo, signal)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) diagnostics.value = null
  } finally {
    if (!signal.aborted) diagnosticsLoading.value = false
  }
}

async function connect(): Promise<void> {
  requestController?.abort()
  destroyPlayer()
  requestController = new AbortController()
  const { signal } = requestController
  state.value = 'loading'
  protocol.value = null
  activeDecoder.value = null
  firstFrameLatencyMs.value = null
  playbackError.value = null
  diagnostics.value = null

  try {
    const devices = await fetchDevices(signal)
    const device = pickDevice(devices)
    selectedDevice.value = device
    if (!device) {
      state.value = 'unavailable'
      return
    }
    if (device.online !== true) {
      state.value = 'offline'
      return
    }

    const channelNo = device.channels.find((channel) => channel.number)?.number ?? 1
    state.value = 'connecting'
    const connectionStartedAt = performance.now()
    const session = await fetchBrowserPlaybackSession(device.device_serial, channelNo, signal)
    protocol.value = session.protocol.toUpperCase()
    void loadDiagnostics(device, channelNo, signal)
    await initializePlayer(session, connectionStartedAt)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      state.value = 'unavailable'
      playbackError.value = '无法创建安全的 EZOPEN 播放会话'
    }
  }
}

function formatBitrate(value: number | null | undefined): string {
  if (!value) return 'Unavailable'
  return `${Math.round(value / 1000)} kbps`
}

onMounted(() => void connect())
onBeforeUnmount(() => {
  requestController?.abort()
  destroyPlayer()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="LIVE MONITOR"
      title="实时监测"
      description="使用萤石官方 EZOPEN 协议低延迟播放真实摄像头；HLS 仅保留给后端诊断与 AI Worker。"
    >
      <template #actions>
        <el-button :icon="Refresh" :loading="state === 'loading'" @click="connect">
          刷新 / 重连
        </el-button>
      </template>
    </PageHeader>

    <section class="monitor-layout">
      <article class="panel-card monitor-workspace">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">CAMERA VIEW</span>
            <h2>{{ deviceDisplayName }}</h2>
          </div>
          <div class="monitor-workspace__tags">
            <el-tag v-if="selectedDevice" effect="plain" :type="selectedDevice.online ? 'success' : 'danger'">
              {{ selectedDevice.online ? 'Online' : 'Offline' }}
            </el-tag>
            <el-tag effect="dark" :type="stateTagType">{{ stateLabel }}</el-tag>
            <el-tag v-if="protocol" effect="plain">{{ protocol }}</el-tag>
            <el-tag v-if="activeDecoder" effect="plain">Decoder {{ activeDecoder }}</el-tag>
          </div>
        </div>

        <div class="monitor-workspace__viewport">
          <div :id="playerContainerId" ref="playerContainer" class="monitor-workspace__player"></div>
          <div v-if="state !== 'live'" class="monitor-workspace__placeholder">
            <el-icon :size="38"><VideoCamera /></el-icon>
            <strong>{{ placeholderMessage }}</strong>
            <span v-if="playbackError">{{ playbackError }}</span>
          </div>
        </div>
        <p class="monitor-workspace__note">
          EZOPEN 首帧出现后自动标记 LIVE；声音受浏览器自动播放策略限制时，请点击播放器音量控件开启。
        </p>
      </article>

      <aside class="panel-card diagnostics-panel">
        <div class="panel-card__header">
          <div>
            <span class="panel-card__kicker">MEDIA DIAGNOSTICS</span>
            <h2>媒体诊断</h2>
          </div>
          <span v-if="diagnosticsLoading" class="panel-card__hint">Probing...</span>
        </div>
        <dl>
          <div><dt>设备</dt><dd>{{ selectedDevice?.model || 'Not detected' }}</dd></div>
          <div><dt>Browser Stream</dt><dd>{{ state === 'live' ? 'Connected' : stateLabel }}</dd></div>
          <div><dt>Browser Protocol</dt><dd>{{ protocol || 'Not connected' }}</dd></div>
          <div><dt>Browser Decoder</dt><dd>{{ activeDecoder || 'Not initialized' }}</dd></div>
          <div><dt>First Frame</dt><dd>{{ firstFrameLatencyMs === null ? 'Not measured' : `${firstFrameLatencyMs} ms` }}</dd></div>
          <div><dt>AI / Probe Protocol</dt><dd>HLS</dd></div>
          <div><dt>Probe</dt><dd>{{ diagnostics?.probe_success ? 'Success' : 'Not probed' }}</dd></div>
          <div><dt>Video Codec</dt><dd>{{ diagnostics?.video?.codec_name || 'Not probed' }}</dd></div>
          <div><dt>Resolution</dt><dd>{{ resolution }}</dd></div>
          <div><dt>FPS</dt><dd>{{ diagnostics?.video?.fps ?? 'Not probed' }}</dd></div>
          <div><dt>Pixel Format</dt><dd>{{ diagnostics?.video?.pixel_format || 'Not probed' }}</dd></div>
          <div><dt>Profile</dt><dd>{{ diagnostics?.video?.profile || 'Not probed' }}</dd></div>
          <div><dt>Video Bitrate</dt><dd>{{ formatBitrate(diagnostics?.video?.bitrate) }}</dd></div>
          <div><dt>Audio</dt><dd>{{ diagnostics ? (diagnostics.audio.available ? 'Available' : 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Audio Codec</dt><dd>{{ diagnostics ? (diagnostics.audio.codec_name || 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Sample Rate</dt><dd>{{ diagnostics ? (diagnostics.audio.sample_rate ? `${diagnostics.audio.sample_rate} Hz` : 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Channels</dt><dd>{{ diagnostics ? (diagnostics.audio.channels ?? 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Audio Bitrate</dt><dd>{{ formatBitrate(diagnostics?.audio.bitrate) }}</dd></div>
        </dl>
        <p>右侧媒体参数由 Backend 通过 HLS + ffprobe 读取；EZOPEN 只负责浏览器低延迟预览。</p>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.monitor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
}

.monitor-workspace__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.monitor-workspace__viewport {
  position: relative;
  min-height: 520px;
  margin-top: 18px;
  overflow: hidden;
  border: 1px solid #283c37;
  border-radius: 11px;
  background: #0c1513;
}

.monitor-workspace__player {
  width: 100%;
  min-height: 520px;
}

.monitor-workspace__placeholder {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 14px;
  color: #9db2ab;
  background: radial-gradient(circle at center, #1a2c27 0, #0c1513 72%);
}

.monitor-workspace__placeholder strong {
  color: #e4efeb;
  font-size: 15px;
}

.monitor-workspace__placeholder span {
  max-width: 430px;
  color: #7f9690;
  font-size: 12px;
  line-height: 1.7;
  text-align: center;
}

.monitor-workspace__note {
  margin: 12px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
  line-height: 1.7;
}

.diagnostics-panel {
  align-self: start;
}

dl {
  margin: 18px 0 0;
}

dl div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 43px;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
}

dt {
  color: var(--color-text-secondary);
  font-size: 12px;
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--color-heading);
  font-size: 11px;
  font-weight: 650;
  text-align: right;
}

.diagnostics-panel > p {
  margin: 18px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
  line-height: 1.7;
}

@media (max-width: 1450px) {
  .monitor-layout {
    grid-template-columns: minmax(0, 1fr) 280px;
  }

  .monitor-workspace__viewport,
  .monitor-workspace__player {
    min-height: 430px;
  }
}
</style>
