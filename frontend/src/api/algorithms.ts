import { requestJson } from './devices'
import type { AlgorithmCapabilities, AlgorithmResult, WorkerStatus } from '../realtime/types'

export interface AlgorithmsStatus {
  redis_reachable: boolean
  workers: WorkerStatus[]
  capabilities: AlgorithmCapabilities
  latest_pipeline_test: AlgorithmResult | null
}

export interface SystemStatus {
  backend: 'online'
  redis: 'healthy' | 'unavailable'
  ai_worker: 'online' | 'offline'
}

export function fetchAlgorithmsStatus(signal?: AbortSignal): Promise<AlgorithmsStatus> {
  return requestJson('/api/algorithms', signal)
}

export function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return requestJson('/api/system/status', signal)
}
