<script setup lang="ts">
import HLSPlayer from '@ezuikit/player-hls'
import { Refresh, VideoCamera } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchDevices, type DeviceSummary } from '../api/devices'
import { fetchLiveStream, fetchMediaInfo, type MediaInfo } from '../api/streams'
import PageHeader from '../components/PageHeader.vue'

type MonitorState =
  | 'loading'
  | 'connecting'
  | 'media-ready'
  | 'live'
  | 'offline'
  | 'unavailable'
  | 'encoding-error'
  | 'error'

const state = ref<MonitorState>('loading')
const selectedDevice = ref<DeviceSummary | null>(null)
const protocol = ref<string | null>(null)
const containerFormat = ref<string | null>(null)
const requestedCodec = ref<string | null>(null)
const activeDecoder = ref<string | null>(null)
const playerPrepared = ref(false)
const diagnostics = ref<MediaInfo | null>(null)
const diagnosticsLoading = ref(false)
const playerContainer = ref<HTMLElement | null>(null)
let player: HLSPlayer | null = null
let requestController: AbortController | null = null
let resizeObserver: ResizeObserver | null = null
let replayTimer: number | null = null
let progressWatchdog: number | null = null
let startPreparedStream: (() => void) | null = null
let recoveryInProgress = false

const stateLabel = computed(() => {
  const labels: Record<MonitorState, string> = {
    loading: 'Loading',
    connecting: 'Connecting',
    'media-ready': 'Verification required',
    live: 'LIVE',
    offline: 'Offline',
    unavailable: 'Unavailable',
    'encoding-error': 'Encoding incompatible',
    error: 'Playback error',
  }
  return labels[state.value]
})

const stateTagType = computed(() => {
  if (state.value === 'live') return 'success'
  if (state.value === 'media-ready') return 'warning'
  if (
    state.value === 'offline' ||
    state.value === 'encoding-error' ||
    state.value === 'error'
  ) return 'danger'
  return 'info'
})

const showBlockingPlaceholder = computed(() =>
  !['media-ready', 'live'].includes(state.value),
)

const placeholderMessage = computed(() => {
  if (state.value === 'loading') return '正在获取设备...'
  if (state.value === 'connecting') {
    return playerPrepared.value ? '播放器已准备，请点击开始实时播放' : '正在连接摄像头...'
  }
  if (state.value === 'offline') return '摄像头当前离线'
  if (state.value === 'encoding-error') return '视频编码或浏览器解码不兼容'
  if (state.value === 'error') return '浏览器播放失败，请尝试重新连接'
  return '暂时无法获取实时视频'
})

const deviceDisplayName = computed(() => {
  const device = selectedDevice.value
  if (!device) return 'EZVIZ Camera'
  if (device.name && device.device_serial && device.name.includes(device.device_serial)) {
    const suffix = device.device_serial.slice(-4)
    return device.name.replace(device.device_serial, `••••${suffix}`)
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
  if (replayTimer !== null) {
    window.clearTimeout(replayTimer)
    replayTimer = null
  }
  if (progressWatchdog !== null) {
    window.clearInterval(progressWatchdog)
    progressWatchdog = null
  }
  startPreparedStream = null
  playerPrepared.value = false
  resizeObserver?.disconnect()
  resizeObserver = null
  if (player) {
    player.destroy()
    player = null
  }
  if (playerContainer.value) {
    playerContainer.value.replaceChildren()
  }
}

async function initializePlayer(
  playbackUrl: string,
  recoverStalledStream: () => void,
): Promise<void> {
  await nextTick()
  const container = playerContainer.value
  if (!container) throw new Error('Player container is unavailable')

  destroyPlayer()
  const width = Math.max(container.clientWidth, 640)
  const height = Math.max(container.clientHeight, 360)
  const currentPlayer = new HLSPlayer({
    container,
    url: playbackUrl,
    type: 'hls',
    width,
    height,
    scaleMode: 0,
    autoPlay: false,
    isLive: true,
    // EZVIZ H.265 live streams require the official client capability marker.
    isEzviz: true,
    // H.265 TS is decoded by the official WASM/WebGL software path rather
    // than relying on browser-native HEVC support.
    decoderType: 'soft',
    staticPath: '/ezuikit-hls/',
    // Keep autoplay reliable. The server still returns audio (mute=0), and
    // the player volume control can be used to enable sound after interaction.
    // The SDK 2.0.0 theme declaration incorrectly narrows this option to the
    // literal false although the runtime and official README accept boolean.
    muted: true as never,
    disableCollect: true,
    language: 'zh',
    loggerOptions: { name: 'CareShield HLS', level: 'WARN', showTime: false },
    // The SDK runtime documents null as the way to disable controls, while
    // its 2.0.0 declaration file accidentally omits null from these fields.
    ptzOptions: null as never,
    talkOptions: null as never,
    capturePictureOptions: null as never,
    recordOptions: null as never,
  })

  const markMediaReady = () => {
    lastProgressAt = Date.now()
    if (state.value === 'connecting') state.value = 'media-ready'
  }
  const markError = (encoding = false) => {
    if (state.value !== 'loading') state.value = 'error'
    if (encoding) state.value = 'encoding-error'
  }
  player = currentPlayer
  currentPlayer.on(HLSPlayer.HLSEVENTS.INIT_SUCCESS, (detail: unknown) => {
    const decoder = (detail as { decoderType?: unknown } | null)?.decoderType
    activeDecoder.value = typeof decoder === 'string' ? decoder : 'soft'
  })
  currentPlayer.on(HLSPlayer.HLSEVENTS.firstFrameDisplay, markMediaReady)
  currentPlayer.on(HLSPlayer.HLSEVENTS.TIME_UPDATE, markMediaReady)
  currentPlayer.on(HLSPlayer.HLSEVENTS.ERROR, () => markError(false))
  currentPlayer.on(HLSPlayer.HLSEVENTS.NETWORK_ERROR, () => markError(false))
  currentPlayer.on(HLSPlayer.HLSEVENTS.MEDIA_ERROR, () => markError(true))
  currentPlayer.on(HLSPlayer.HLSEVENTS.WASM_FAILED, () => markError(true))

  let lastProgressAt = Date.now()
  let playPending = false
  const playCurrentStream = () => {
    if (player !== currentPlayer || playPending) return
    playPending = true
    lastProgressAt = Date.now()
    void currentPlayer
      .play(playbackUrl)
      .catch((error: unknown) => {
        if (player !== currentPlayer) return
        if (error instanceof DOMException && error.name === 'AbortError') return
        markError(false)
      })
      .finally(() => {
        playPending = false
      })
  }
  currentPlayer.on(HLSPlayer.HLSEVENTS.ENDED, () => {
    if (player !== currentPlayer) return
    replayTimer = window.setTimeout(recoverStalledStream, 250)
  })
  // The official compatibility table does not expose `ended` for H.265.
  // Reload a live playlist when media progress stops instead of treating the
  // last decoded frame as an active stream.
  progressWatchdog = window.setInterval(() => {
    if (player !== currentPlayer || !['media-ready', 'live'].includes(state.value)) return
    if (Date.now() - lastProgressAt > 4_000) {
      lastProgressAt = Date.now()
      recoverStalledStream()
    }
  }, 2_000)
  startPreparedStream = playCurrentStream
  playerPrepared.value = true

  resizeObserver = new ResizeObserver(([entry]) => {
    if (!entry || !player) return
    player.resize(Math.max(entry.contentRect.width, 1), Math.max(entry.contentRect.height, 1))
  })
  resizeObserver.observe(container)
}

async function recoverPlayback(
  device: DeviceSummary,
  channelNo: number,
  signal: AbortSignal,
): Promise<void> {
  if (recoveryInProgress || signal.aborted) return
  recoveryInProgress = true
  try {
    const playback = await fetchLiveStream(device.device_serial, channelNo, signal)
    protocol.value = playback.protocol.toUpperCase()
    containerFormat.value = playback.container.toUpperCase()
    requestedCodec.value = playback.requested_video_codec.toUpperCase()
    await initializePlayer(
      playback.playback_url,
      () => void recoverPlayback(device, channelNo, signal),
    )
    startPreparedStream?.()
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      state.value = 'error'
    }
  } finally {
    recoveryInProgress = false
  }
}

function startPlayback(): void {
  startPreparedStream?.()
}

async function loadDiagnostics(device: DeviceSummary, channelNo: number, signal: AbortSignal) {
  diagnosticsLoading.value = true
  diagnostics.value = null
  try {
    diagnostics.value = await fetchMediaInfo(device.device_serial, channelNo, signal)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      diagnostics.value = null
    }
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
  recoveryInProgress = false
  protocol.value = null
  containerFormat.value = null
  requestedCodec.value = null
  activeDecoder.value = null
  playerPrepared.value = false
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
    const playback = await fetchLiveStream(device.device_serial, channelNo, signal)
    protocol.value = playback.protocol.toUpperCase()
    containerFormat.value = playback.container.toUpperCase()
    requestedCodec.value = playback.requested_video_codec.toUpperCase()
    void loadDiagnostics(device, channelNo, signal)
    await initializePlayer(
      playback.playback_url,
      () => void recoverPlayback(device, channelNo, signal),
    )
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      state.value = 'unavailable'
    }
  }
}

function confirmCameraContent(): void {
  if (state.value === 'media-ready') state.value = 'live'
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
      description="通过 CareShield Backend 获取临时 HLS 地址，播放真实萤石摄像头实时画面。"
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
            <el-tag v-if="requestedCodec" effect="plain">{{ requestedCodec }}</el-tag>
          </div>
        </div>

        <div class="monitor-workspace__viewport">
          <div ref="playerContainer" class="monitor-workspace__player"></div>
          <div v-if="showBlockingPlaceholder" class="monitor-workspace__placeholder">
            <el-icon :size="38"><VideoCamera /></el-icon>
            <strong>{{ placeholderMessage }}</strong>
            <span v-if="state === 'error' || state === 'unavailable'">
              播放地址不会被保存；可使用上方按钮重新获取临时地址。
            </span>
            <el-button
              v-if="state === 'connecting' && playerPrepared"
              type="primary"
              @click="startPlayback"
            >
              开始实时播放
            </el-button>
          </div>
        </div>
        <div v-if="state === 'media-ready'" class="monitor-workspace__verification">
          <div>
            <strong>请进行人工画面确认</strong>
            <span>确认当前显示的是摄像机实时内容，而不是萤石平台生成的错误提示视频。</span>
          </div>
          <el-button type="warning" plain @click="confirmCameraContent">
            确认这是实时画面
          </el-button>
        </div>
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
          <div><dt>Stream</dt><dd>{{ ['media-ready', 'live'].includes(state) ? 'Decoded' : stateLabel }}</dd></div>
          <div><dt>Camera Content</dt><dd>{{ state === 'live' ? 'Manually verified' : 'Verification required' }}</dd></div>
          <div><dt>Requested Codec</dt><dd>{{ requestedCodec || 'Not requested' }}</dd></div>
          <div><dt>Container</dt><dd>{{ containerFormat || 'Not requested' }}</dd></div>
          <div><dt>Browser Decoder</dt><dd>{{ activeDecoder || 'Not initialized' }}</dd></div>
          <div><dt>Probe</dt><dd>{{ diagnostics?.probe_success ? 'Success' : 'Not probed' }}</dd></div>
          <div><dt>Video Codec</dt><dd>{{ diagnostics?.video?.codec_name || 'Not probed' }}</dd></div>
          <div><dt>Resolution</dt><dd>{{ resolution }}</dd></div>
          <div><dt>FPS</dt><dd>{{ diagnostics?.video?.fps ?? 'Not probed' }}</dd></div>
          <div><dt>Pixel Format</dt><dd>{{ diagnostics?.video?.pixel_format || 'Not probed' }}</dd></div>
          <div><dt>Profile</dt><dd>{{ diagnostics?.video?.profile || 'Not probed' }}</dd></div>
          <div><dt>Video Bitrate</dt><dd>{{ formatBitrate(diagnostics?.video?.bitrate) }}</dd></div>
          <div>
            <dt>Audio</dt>
            <dd>{{ diagnostics ? (diagnostics.audio.available ? 'Available' : 'Unavailable') : 'Not probed' }}</dd>
          </div>
          <div><dt>Audio Codec</dt><dd>{{ diagnostics ? (diagnostics.audio.codec_name || 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Sample Rate</dt><dd>{{ diagnostics ? (diagnostics.audio.sample_rate ? `${diagnostics.audio.sample_rate} Hz` : 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Channels</dt><dd>{{ diagnostics ? (diagnostics.audio.channels ?? 'Unavailable') : 'Not probed' }}</dd></div>
          <div><dt>Audio Bitrate</dt><dd>{{ formatBitrate(diagnostics?.audio.bitrate) }}</dd></div>
        </dl>
        <p>诊断数据由 Backend ffprobe 实时读取，不包含播放地址或访问凭据。</p>
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

.monitor-workspace__verification {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgb(230 162 60 / 55%);
  border-radius: 9px;
  color: #f4d7a2;
  background: rgb(12 21 19 / 90%);
  font-size: 12px;
}

.monitor-workspace__verification > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.monitor-workspace__verification strong {
  color: #ffe1ac;
  font-size: 13px;
}

.monitor-workspace__verification span {
  color: #b8c9c4;
  line-height: 1.6;
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
