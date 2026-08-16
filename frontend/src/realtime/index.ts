import { ref } from 'vue'

import { RealtimeClient, type RealtimeConnectionStatus } from './RealtimeClient'
import type { AlgorithmResult, WorkerStatus } from './types'

function realtimeUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/realtime`
}

const client = new RealtimeClient({ url: realtimeUrl() })

export const realtimeStatus = ref<RealtimeConnectionStatus>('disconnected')
export const lastRealtimeMessageAt = ref<string | null>(null)
export const latestWorkerStatus = ref<WorkerStatus | null>(null)
export const latestPipelineTest = ref<AlgorithmResult | null>(null)
export const latestPipelineLatencyMs = ref<number | null>(null)

client.onStatus((status) => {
  realtimeStatus.value = status
})

client.onMessage((envelope) => {
  lastRealtimeMessageAt.value = new Date().toISOString()
  if (envelope.type === 'worker_status') {
    latestWorkerStatus.value = envelope.data as WorkerStatus
    return
  }
  const result = envelope.data as AlgorithmResult
  if (result.task === 'pipeline_test' && result.simulated) {
    latestPipelineTest.value = result
    latestPipelineLatencyMs.value = Math.max(0, Date.now() - Date.parse(result.result_timestamp))
  }
})

export function connectRealtime(): void {
  client.connect()
}

export function disconnectRealtime(): void {
  client.disconnect()
}
