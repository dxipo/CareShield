export type RealtimeMessageType = 'algorithm_result' | 'worker_status'
export type AlgorithmTask =
  | 'fall_detection'
  | 'fall_risk'
  | 'fraud_detection'
  | 'pipeline_test'
export type CapabilityState =
  | 'not_installed'
  | 'installed'
  | 'starting'
  | 'running'
  | 'unavailable'
  | 'error'

export interface AlgorithmCapabilities {
  fall_detection: CapabilityState
  fall_risk: CapabilityState
  fraud_detection: CapabilityState
}

export interface AlgorithmResult {
  result_id: string
  task: AlgorithmTask
  model_id: string
  model_version: string
  device_id: string | null
  source_timestamp: string | null
  result_timestamp: string
  label: string
  score: number | null
  level: 'normal' | 'low' | 'medium' | 'high' | 'critical' | null
  latency_ms: number | null
  metadata: Record<string, unknown>
  simulated: boolean
}

export interface WorkerStatus {
  worker_id: string
  online: boolean
  timestamp: string
  version: string
  capabilities: AlgorithmCapabilities
  runtime: Record<string, unknown>
}

export interface AlgorithmResultEnvelope {
  type: 'algorithm_result'
  timestamp: string
  data: AlgorithmResult
}

export interface WorkerStatusEnvelope {
  type: 'worker_status'
  timestamp: string
  data: WorkerStatus
}

export type RealtimeEnvelope = AlgorithmResultEnvelope | WorkerStatusEnvelope

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isAlgorithmResult(value: unknown): value is AlgorithmResult {
  if (!isRecord(value)) return false
  const tasks: AlgorithmTask[] = [
    'fall_detection',
    'fall_risk',
    'fraud_detection',
    'pipeline_test',
  ]
  return (
    typeof value.result_id === 'string' &&
    typeof value.task === 'string' &&
    tasks.includes(value.task as AlgorithmTask) &&
    typeof value.model_id === 'string' &&
    typeof value.model_version === 'string' &&
    typeof value.result_timestamp === 'string' &&
    typeof value.label === 'string' &&
    typeof value.simulated === 'boolean' &&
    isRecord(value.metadata)
  )
}

function isCapabilities(value: unknown): value is AlgorithmCapabilities {
  if (!isRecord(value)) return false
  const states: CapabilityState[] = [
    'not_installed',
    'installed',
    'starting',
    'running',
    'unavailable',
    'error',
  ]
  return (
    states.includes(value.fall_detection as CapabilityState) &&
    states.includes(value.fall_risk as CapabilityState) &&
    states.includes(value.fraud_detection as CapabilityState)
  )
}

function isWorkerStatus(value: unknown): value is WorkerStatus {
  if (!isRecord(value)) return false
  return (
    typeof value.worker_id === 'string' &&
    typeof value.online === 'boolean' &&
    typeof value.timestamp === 'string' &&
    typeof value.version === 'string' &&
    isCapabilities(value.capabilities) &&
    isRecord(value.runtime)
  )
}

export function parseRealtimeMessage(raw: string): RealtimeEnvelope | null {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isRecord(value) || typeof value.timestamp !== 'string') return null
  if (value.type === 'algorithm_result' && isAlgorithmResult(value.data)) {
    return value as unknown as AlgorithmResultEnvelope
  }
  if (value.type === 'worker_status' && isWorkerStatus(value.data)) {
    return value as unknown as WorkerStatusEnvelope
  }
  return null
}
